from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from ..config import Settings


class SyllabusInterpreterAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="SyllabusInterpreterAgent",
            goal="Transform a concept into clear, grade-level coverage objectives.",
            backstory="Curriculum expert who decomposes school concepts into teachable parts.",
        )

    def execute(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        learner_profile: str | None,
    ) -> dict[str, Any]:
        prompt = (
            f"Subject: {subject_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Concept: {concept_name}\n"
            f"Concept Description: {concept_description or 'N/A'}\n"
            f"Learner Profile: {learner_profile or 'General classroom learner'}\n\n"
            "Create a concise coverage map with keys: objectives (list), prerequisites (list), misconceptions (list). "
            "Keep outputs simple and student-friendly. "
            "Strict rule: output must be only for this exact concept and grade level; do not include unrelated concepts."
        )
        data = self.run_json_task(
            prompt,
            required_keys=["objectives", "prerequisites", "misconceptions"],
        )
        objectives = self.to_list(data.get("objectives"), [])
        prerequisites = self.to_list(data.get("prerequisites"), [])
        misconceptions = self.to_list(data.get("misconceptions"), [])
        if not objectives or not prerequisites or not misconceptions:
            raise ValueError("SyllabusInterpreterAgent produced incomplete concept mapping.")
        return {
            "objectives": objectives[:6],
            "prerequisites": prerequisites[:5],
            "misconceptions": misconceptions[:6],
        }
