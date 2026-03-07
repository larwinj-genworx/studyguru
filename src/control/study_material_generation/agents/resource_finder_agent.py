from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import BaseStructuredAgent
from ..retrieval import EvidenceRetrievalService
from src.config.settings import Settings


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
        api_key = (self.settings.youtube_api_key or "").strip()
        if not api_key:
            return []

        query = f"{grade_level} {subject_name} {concept_name} tutorial"
        search_url = "https://www.googleapis.com/youtube/v3/search"
        videos_url = "https://www.googleapis.com/youtube/v3/videos"
        timeout = httpx.Timeout(min(self.settings.resource_search_timeout_seconds, 8))

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                search_response = await client.get(
                    search_url,
                    params={
                        "part": "snippet",
                        "q": query,
                        "type": "video",
                        "maxResults": 8,
                        "safeSearch": "strict",
                        "videoEmbeddable": "true",
                        "relevanceLanguage": "en",
                        "order": "viewCount",
                        "key": api_key,
                    },
                )
                if search_response.status_code >= 400:
                    return []
                search_data = search_response.json()
                items = search_data.get("items", []) if isinstance(search_data, dict) else []
                video_ids = [
                    item.get("id", {}).get("videoId")
                    for item in items
                    if isinstance(item, dict)
                ]
                video_ids = [vid for vid in video_ids if vid]
                if not video_ids:
                    return []

                videos_response = await client.get(
                    videos_url,
                    params={
                        "part": "snippet,statistics",
                        "id": ",".join(video_ids[:8]),
                        "key": api_key,
                    },
                )
                if videos_response.status_code >= 400:
                    return []
                videos_data = videos_response.json()
                video_items = videos_data.get("items", []) if isinstance(videos_data, dict) else []
        except Exception as exc:
            self._logger.warning("[ResourceFinderAgent] YouTube fetch failed: %s", exc)
            return []

        ranked: list[dict[str, Any]] = []
        for item in video_items:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id")
            snippet = item.get("snippet", {}) or {}
            stats = item.get("statistics", {}) or {}
            if not video_id:
                continue
            try:
                views = int(stats.get("viewCount", 0))
            except (TypeError, ValueError):
                views = 0
            try:
                likes = int(stats.get("likeCount", 0))
            except (TypeError, ValueError):
                likes = 0
            ranked.append(
                {
                    "title": str(snippet.get("title", "YouTube Lesson")).strip(),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "views": views,
                    "likes": likes,
                }
            )

        if not ranked:
            return []

        ranked.sort(key=lambda item: (item["views"], item["likes"]), reverse=True)
        best = ranked[0]
        note = f"YouTube video (views: {best['views']:,}, likes: {best['likes']:,})"
        return [
            {
                "title": best["title"][:120],
                "url": best["url"],
                "note": note[:240],
            }
        ]
