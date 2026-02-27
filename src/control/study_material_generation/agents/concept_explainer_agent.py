from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from ..config import Settings


class ConceptExplainerAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="ConceptExplainerAgent",
            goal="Produce concise explanation, intuition, steps, and recap.",
            backstory="Friendly subject teacher for school learners.",
        )

    def execute(
        self,
        *,
        concept_name: str,
        grade_level: str,
        coverage_map: dict[str, Any],
        teaching_plan: dict[str, Any],
        revision_feedback: str | None,
    ) -> dict[str, Any]:
        prompt = (
            f"Concept: {concept_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Coverage: {coverage_map}\n"
            f"Teaching Plan: {teaching_plan}\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n\n"
            "Return JSON with keys: definition (string), intuition (string), formulas (list), "
            "key_steps (list), common_mistakes (list), recap (list), "
            "practical_examples_required (boolean). "
            "Definition should be 70-110 words. Intuition should be 3-5 short sentences. "
            "Provide 6-9 key_steps, 4-6 common_mistakes, and 4-6 recap bullets. "
            "Formulas: include only if the concept truly uses equations/formulae; otherwise return an empty list. "
            "Set practical_examples_required to false only when the concept is purely theoretical "
            "and does not lend itself to realistic practical examples. "
            "If Revision Feedback is provided, fix those issues first. "
            "Strict rule: explanation must remain fully concept-specific and should not mention unrelated topics. "
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(
            prompt,
            required_keys=[
                "definition",
                "intuition",
                "key_steps",
                "common_mistakes",
                "recap",
                "formulas",
                "practical_examples_required",
            ],
        )
        definition = str(data.get("definition", "")).strip()
        intuition = str(data.get("intuition", "")).strip()
        formulas = self.to_list(data.get("formulas"), [])
        key_steps = self.to_list(data.get("key_steps"), [])
        common_mistakes = self.to_list(data.get("common_mistakes"), [])
        recap = self.to_list(data.get("recap"), [])
        if not definition or not intuition or not key_steps or not common_mistakes or not recap:
            raise ValueError("ConceptExplainerAgent produced incomplete core notes.")

        def _to_bool(value: Any, default: bool = True) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"false", "no", "0", "not required"}:
                    return False
                if normalized in {"true", "yes", "1", "required"}:
                    return True
            return default

        def _limit_words(text: str, max_words: int) -> str:
            words = text.split()
            if len(words) <= max_words:
                return text
            return " ".join(words[:max_words]).strip()

        definition = _limit_words(definition, 140)
        intuition = _limit_words(intuition, 90)
        formulas = [str(item).strip() for item in formulas if str(item).strip()][:6]
        practical_examples_required = _to_bool(data.get("practical_examples_required"), default=True)
        return {
            "definition": definition,
            "intuition": intuition,
            "formulas": formulas,
            "key_steps": key_steps[:10],
            "common_mistakes": common_mistakes[:8],
            "recap": recap[:8],
            "practical_examples_required": practical_examples_required,
        }
