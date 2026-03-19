from __future__ import annotations

from src.config.settings import Settings
from src.control.study_material_generation.retrieval.service import EvidenceRetrievalService

from .models import BotEvidenceChunk


class LearningBotExternalRetriever:
    def __init__(self, settings: Settings) -> None:
        self.service = EvidenceRetrievalService(settings)
        self.settings = settings

    async def retrieve(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        question: str,
        max_chunks: int,
    ) -> list[BotEvidenceChunk]:
        payload = await self.service.gather(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
            concept_description=concept_description,
            query_focus=question,
        )
        snippets = payload.get("evidence_snippets") or []
        chunks: list[BotEvidenceChunk] = []
        for item in snippets[: max(max_chunks, 1)]:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            label = str(item.get("source_title", "")).strip() or str(item.get("domain", "External source")).strip()
            chunks.append(
                BotEvidenceChunk(
                    label=label[:140],
                    text=text,
                    score=float(item.get("score", 0.0) or 0.0),
                    source_type="external",
                    url=str(item.get("source_url", "")).strip() or None,
                    note=str(item.get("domain", "")).strip() or "External source",
                )
            )
        return chunks
