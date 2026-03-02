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

        guidance = []
        guidance_map = {
            "Definition is too short.": "Expand the definition with context, scope, and one practical use case.",
            "Definition is too long.": "Trim the definition to the core idea and remove repetition.",
            "Need at least 3 practical examples.": "Add worked examples that show step-by-step reasoning.",
            "Need at least 6 MCQs.": "Add more MCQs that test concept understanding and application.",
            "Need at least 8 flashcards.": "Add recall flashcards covering terms, steps, and pitfalls.",
            "Need at least one validated reference.": "Add at least one reputable learning resource link.",
        }
        for issue in issues:
            guidance.append(guidance_map.get(issue, "Strengthen clarity and completeness for this concept."))
        if not guidance and issues:
            guidance = ["Simplify language, strengthen examples, and add clearer practice coverage."]

        approved = not issues

        return {
            "approved": approved,
            "issues": issues[:8],
            "guidance": guidance[:8],
        }
