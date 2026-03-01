from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class QualityGuardianAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="QualityGuardianAgent",
            goal="Validate clarity, completeness, and student-friendliness.",
            backstory="Instructional quality reviewer for school study material.",
        )

    def execute(
        self,
        *,
        concept_name: str,
        content: dict[str, Any],
        resource_required: bool = True,
    ) -> dict[str, Any]:
        prompt = (
            f"Concept: {concept_name}\n"
            f"Content Draft: {content}\n\n"
            "Return JSON with keys: approved (boolean), issues (list), guidance (list). "
            "Check brevity, correctness, and coverage."
        )
        data = self.run_json_task(prompt) or {}

        issues: list[str] = []
        definition_word_count = len(str(content.get("definition", "")).split())
        if definition_word_count < 55:
            issues.append("Definition is too short.")
        if definition_word_count > 150:
            issues.append("Definition is too long.")
        practical_required = bool(content.get("practical_examples_required", True))
        if practical_required and len(content.get("examples", [])) < 3:
            issues.append("Need at least 3 practical examples.")
        if len(content.get("mcqs", [])) < 6:
            issues.append("Need at least 6 MCQs.")
        if len(content.get("flashcards", [])) < 8:
            issues.append("Need at least 8 flashcards.")
        if resource_required and len(content.get("references", [])) < 1:
            issues.append("Need at least one validated reference.")

        model_guidance = [
            str(item).strip()
            for item in data.get("issues", [])
            if str(item).strip()
        ]
        model_guidance.extend(
            str(item).strip()
            for item in data.get("guidance", [])
            if str(item).strip()
        )

        guidance = []
        seen: set[str] = set()
        for item in model_guidance:
            if item not in seen:
                seen.add(item)
                guidance.append(item)
        if not guidance and issues:
            guidance = ["Simplify language, strengthen examples, and add clearer practice coverage."]

        approved = not issues

        return {
            "approved": approved,
            "issues": issues[:8],
            "guidance": guidance[:8],
        }
