from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from ..config import Settings


class StudentPedagogyAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="StudentPedagogyAgent",
            goal="Create an engaging, low-friction teaching plan for the concept.",
            backstory="Pedagogy planner focused on easy understanding and student attention.",
        )

    def execute(
        self,
        *,
        concept_name: str,
        grade_level: str,
        coverage_map: dict[str, Any],
        learner_profile: str | None,
    ) -> dict[str, Any]:
        prompt = (
            f"Concept: {concept_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Coverage Map: {coverage_map}\n"
            f"Learner Profile: {learner_profile or 'General classroom learner'}\n\n"
            "Create JSON with keys: lesson_flow (list), teaching_tips (list). "
            "Keep sentences short and progression gradual. "
            "Strict rule: design pedagogy only for this concept and avoid generic reusable text."
        )
        data = self.run_json_task(
            prompt,
            required_keys=["lesson_flow", "teaching_tips"],
        )
        lesson_flow = self.to_list(data.get("lesson_flow"), [])
        teaching_tips = self.to_list(data.get("teaching_tips"), [])
        if not lesson_flow or not teaching_tips:
            raise ValueError("StudentPedagogyAgent produced incomplete pedagogical flow.")
        return {
            "lesson_flow": lesson_flow[:7],
            "teaching_tips": teaching_tips[:6],
        }
