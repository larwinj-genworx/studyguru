from __future__ import annotations

import logging
from typing import Any

from src.config.settings import Settings
from src.core.services.resource_video_service import YouTubeVideoService
from .base import BaseStructuredAgent
from ..retrieval import EvidenceRetrievalService


class ResourceUnavailableError(RuntimeError):
    """Raised when no external resources can be found for a concept."""


class ResourceFinderAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="ResourceFinderAgent",
            goal="Collect grounded learning evidence and learner-friendly references.",
            backstory="Academic research curator who gathers trustworthy source material for study generation.",
        )
        self._logger = logging.getLogger("uvicorn.error")
        self._evidence_service = EvidenceRetrievalService(settings)
        self._video_service = YouTubeVideoService(settings)

    async def execute(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None = None,
    ) -> dict[str, Any]:
        evidence_pack = await self._evidence_service.gather(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
            concept_description=concept_description,
        )
        youtube_resources = await self._youtube_candidates(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
        )

        merged_references = self._merge_references(
            evidence_pack.get("references", []),
            youtube_resources,
        )
        if not merged_references:
            merged_references = self._fallback_references(concept_name, subject_name)
            evidence_pack["retrieval_status"] = "fallback"
            evidence_pack["coverage_summary"] = (
                "External evidence retrieval was limited; fallback references were added "
                "so the concept can still be generated without blocking the job."
            )

        evidence_pack["references"] = merged_references[:8]
        evidence_pack["resource_required"] = bool(evidence_pack.get("source_documents")) or bool(
            evidence_pack.get("evidence_snippets")
        )
        return evidence_pack

    @staticmethod
    def _merge_references(*reference_sets: list[dict[str, str]]) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for reference_set in reference_sets:
            if not isinstance(reference_set, list):
                continue
            for item in reference_set:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url", "")).strip()
                title = str(item.get("title", "Resource")).strip() or "Resource"
                note = str(item.get("note", "")).strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(
                    {
                        "title": title[:120],
                        "url": url,
                        "note": note[:240] if note else "Learning resource",
                    }
                )
        return merged

    async def _youtube_candidates(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
    ) -> list[dict[str, str]]:
        candidate = await self._video_service.find_best_video(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
        )
        if not candidate:
            return []
        note = f"YouTube video (views: {candidate['views']:,}, likes: {candidate['likes']:,})"
        return [
            {
                "title": candidate["title"][:120],
                "url": candidate["url"],
                "note": note[:240],
            }
        ]
