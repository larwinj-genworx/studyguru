from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from src.config.settings import Settings
from src.schemas.study_material import LearningContent

from ..agents import LearningBotAgentRegistry
from ..retrieval import BotEvidenceChunk, ConceptContentRetriever, LearningBotExternalRetriever


logger = logging.getLogger("uvicorn.error")


@dataclass(slots=True)
class LearningBotReply:
    answer: str
    citations: list[dict[str, Any]]
    follow_up_suggestions: list[str]
    meta: dict[str, Any]


class LearningBotChatEngine:
    def __init__(self, settings: Settings, agents: LearningBotAgentRegistry) -> None:
        self.settings = settings
        self.agents = agents
        self.content_retriever = ConceptContentRetriever()
        self.external_retriever = LearningBotExternalRetriever(settings)

    async def generate_reply(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_id: str,
        concept_name: str,
        concept_description: str | None,
        material_version: int,
        content: LearningContent,
        recent_history: list[dict[str, str]],
        student_message: str,
    ) -> LearningBotReply:
        response_mode = self._resolve_response_mode(student_message)
        internal_chunks = self.content_retriever.retrieve(
            concept_id=concept_id,
            material_version=material_version,
            concept_name=concept_name,
            content=content,
            query=student_message,
            max_chunks=self.settings.learning_bot_max_internal_chunks,
        )
        internal_top_score = internal_chunks[0].score if internal_chunks else 0.0
        logger.info(
            "[LearningBot] Internal retrieval completed for concept='%s'. chunks=%d top_score=%.4f mode=%s",
            concept_name,
            len(internal_chunks),
            internal_top_score,
            response_mode,
        )

        external_chunks: list[BotEvidenceChunk] = []
        if self._should_use_external(student_message, internal_chunks):
            external_chunks = await self.external_retriever.retrieve(
                subject_name=subject_name,
                grade_level=grade_level,
                concept_name=concept_name,
                concept_description=concept_description,
                question=student_message,
                max_chunks=self.settings.learning_bot_max_external_chunks,
            )
            logger.info(
                "[LearningBot] External retrieval completed for concept='%s'. chunks=%d",
                concept_name,
                len(external_chunks),
            )

        evidence = self._assign_source_ids(
            internal_chunks=internal_chunks,
            external_chunks=external_chunks,
        )
        retrieval_mode = self._resolve_retrieval_mode(internal_chunks, external_chunks)
        prompt_blocks = [chunk.to_prompt_block() for chunk in evidence]

        try:
            payload = await asyncio.to_thread(
                self.agents.response.execute,
                subject_name=subject_name,
                grade_level=grade_level,
                concept_name=concept_name,
                concept_description=concept_description,
                response_mode=response_mode,
                student_message=student_message,
                recent_history=recent_history[-self.settings.learning_bot_history_limit :],
                evidence_blocks=prompt_blocks,
            )
        except Exception as exc:
            logger.warning(
                "[LearningBot] Falling back to deterministic response for concept='%s': %s",
                concept_name,
                exc,
            )
            payload = self._build_fallback_response(
                concept_name=concept_name,
                student_message=student_message,
                response_mode=response_mode,
                evidence=evidence,
            )

        answer = self._normalize_answer(str(payload.get("answer", "")))
        if not answer:
            payload = self._build_fallback_response(
                concept_name=concept_name,
                student_message=student_message,
                response_mode=response_mode,
                evidence=evidence,
            )
            answer = self._normalize_answer(str(payload.get("answer", "")))

        citations = self._collect_citations(
            requested_source_ids=payload.get("used_source_ids"),
            evidence=evidence,
        )
        follow_ups = self._clean_follow_ups(payload.get("follow_up_suggestions"), concept_name=concept_name)
        confidence = str(payload.get("confidence", "")).strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium" if citations else "low"

        logger.info(
            "[LearningBot] Reply ready for concept='%s'. retrieval_mode=%s citations=%d confidence=%s",
            concept_name,
            retrieval_mode,
            len(citations),
            confidence,
        )
        return LearningBotReply(
            answer=answer,
            citations=citations,
            follow_up_suggestions=follow_ups,
            meta={
                "response_mode": response_mode,
                "retrieval_mode": retrieval_mode,
                "confidence": confidence,
                "internal_top_score": round(internal_top_score, 4),
                "internal_chunks": len(internal_chunks),
                "external_chunks": len(external_chunks),
            },
        )

    def _resolve_response_mode(self, message: str) -> str:
        lowered = message.lower()
        if any(token in lowered for token in ("quiz", "practice", "mcq", "test me")):
            return "practice"
        if any(token in lowered for token in ("step by step", "derive", "show steps", "how do i", "how to")):
            return "step_by_step"
        if any(token in lowered for token in ("simple", "easier", "easy language", "beginner", "simplify")):
            return "simplify"
        return "explain"

    def _should_use_external(self, message: str, internal_chunks: list[BotEvidenceChunk]) -> bool:
        lowered = message.lower()
        if any(
            token in lowered
            for token in (
                "latest",
                "recent",
                "research",
                "outside",
                "reference",
                "source",
                "real world",
                "application",
                "applications",
                "further reading",
            )
        ):
            return True
        top_score = internal_chunks[0].score if internal_chunks else 0.0
        return top_score < self.settings.learning_bot_external_trigger_score

    @staticmethod
    def _assign_source_ids(
        *,
        internal_chunks: list[BotEvidenceChunk],
        external_chunks: list[BotEvidenceChunk],
    ) -> list[BotEvidenceChunk]:
        evidence: list[BotEvidenceChunk] = []
        for index, chunk in enumerate(internal_chunks, start=1):
            chunk.source_id = f"I{index}"
            evidence.append(chunk)
        for index, chunk in enumerate(external_chunks, start=1):
            chunk.source_id = f"E{index}"
            evidence.append(chunk)
        return evidence

    @staticmethod
    def _resolve_retrieval_mode(
        internal_chunks: list[BotEvidenceChunk],
        external_chunks: list[BotEvidenceChunk],
    ) -> str:
        if internal_chunks and external_chunks:
            return "hybrid"
        if internal_chunks:
            return "internal_only"
        if external_chunks:
            return "external_only"
        return "unavailable"

    def _build_fallback_response(
        self,
        *,
        concept_name: str,
        student_message: str,
        response_mode: str,
        evidence: list[BotEvidenceChunk],
    ) -> dict[str, Any]:
        lead = f"Here is a grounded explanation for {concept_name} based on your current lesson."
        if response_mode == "practice":
            lead = f"Here is a quick practice set for {concept_name} based on your lesson."
        selected = evidence[:2]
        if not selected:
            answer = (
                f"I could not find enough grounded lesson evidence to answer this clearly for {concept_name}. "
                "Please try asking in a more specific way."
            )
        else:
            detail_lines = [chunk.text for chunk in selected if chunk.text]
            answer = f"{lead}\n\n" + "\n\n".join(detail_lines)
            if response_mode == "practice":
                answer += (
                    f"\n\nPractice:\n1. Explain the main idea behind {concept_name}.\n"
                    f"2. Solve one short example from {concept_name}.\n"
                    "3. State one common mistake and how to avoid it."
                )
        return {
            "answer": answer,
            "used_source_ids": [chunk.source_id for chunk in selected],
            "follow_up_suggestions": [
                f"Explain {concept_name} in simpler words",
                f"Give me one worked example on {concept_name}",
                f"Test me on {concept_name}",
            ],
            "confidence": "medium" if selected else "low",
        }

    @staticmethod
    def _collect_citations(
        *,
        requested_source_ids: Any,
        evidence: list[BotEvidenceChunk],
    ) -> list[dict[str, Any]]:
        evidence_map = {chunk.source_id: chunk for chunk in evidence if chunk.source_id}
        citations: list[dict[str, Any]] = []
        source_ids = requested_source_ids if isinstance(requested_source_ids, list) else []
        for item in source_ids:
            source_id = str(item).strip()
            chunk = evidence_map.get(source_id)
            if not chunk:
                continue
            citations.append(chunk.to_citation())
        if citations:
            return citations[:4]
        return [chunk.to_citation() for chunk in evidence[:2]]

    @staticmethod
    def _clean_follow_ups(raw: Any, *, concept_name: str) -> list[str]:
        if not isinstance(raw, list):
            raw = []
        cleaned = [str(item).strip() for item in raw if str(item).strip()]
        defaults = [
            f"Explain {concept_name} in simpler words",
            f"Give me one example from {concept_name}",
            f"Ask me 3 practice questions on {concept_name}",
        ]
        combined: list[str] = []
        for item in [*cleaned, *defaults]:
            if item not in combined:
                combined.append(item)
            if len(combined) >= 3:
                break
        return combined

    @staticmethod
    def _normalize_answer(value: str) -> str:
        cleaned = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned
