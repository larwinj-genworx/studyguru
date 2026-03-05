from __future__ import annotations

from typing import Any

from src.config.settings import Settings
from src.control.student_quiz_generation.agents import QuizAgentRegistry


class QuizEngine:
    def __init__(self, settings: Settings, agents: QuizAgentRegistry) -> None:
        self.settings = settings
        self.agents = agents

    def generate_mcqs(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_summary: str,
        key_points: list[str],
        common_mistakes: list[str],
        question_count: int,
        revision_feedback: str | None = None,
    ) -> list[dict[str, Any]]:
        payload = self.agents.quiz_item.execute(
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=concept_name,
            concept_summary=concept_summary,
            key_points=key_points,
            common_mistakes=common_mistakes,
            question_count=question_count,
            revision_feedback=revision_feedback,
        )
        mcqs = payload.get("mcqs", [])
        return mcqs if isinstance(mcqs, list) else []
