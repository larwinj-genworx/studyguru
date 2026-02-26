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
            "Return JSON with keys: definition (string), intuition (string), key_steps (list), "
            "common_mistakes (list), recap (list). "
            "Definition should be 35-70 words. Intuition should be 2-3 short sentences. "
            "Provide 4-6 key_steps, 3-5 common_mistakes, and 3-5 recap bullets. "
            "If Revision Feedback is provided, fix those issues first. "
            "Strict rule: explanation must remain fully concept-specific and should not mention unrelated topics. "
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(
            prompt,
            required_keys=["definition", "intuition", "key_steps", "common_mistakes", "recap"],
        )
        definition = str(data.get("definition", "")).strip()
        intuition = str(data.get("intuition", "")).strip()
        key_steps = self.to_list(data.get("key_steps"), [])
        common_mistakes = self.to_list(data.get("common_mistakes"), [])
        recap = self.to_list(data.get("recap"), [])
        if not definition or not intuition or not key_steps or not common_mistakes or not recap:
            raise ValueError("ConceptExplainerAgent produced incomplete core notes.")

        def _limit_words(text: str, max_words: int) -> str:
            words = text.split()
            if len(words) <= max_words:
                return text
            return " ".join(words[:max_words]).strip()

        definition = _limit_words(definition, 80)
        intuition = _limit_words(intuition, 60)
        return {
            "definition": definition,
            "intuition": intuition,
            "key_steps": key_steps[:8],
            "common_mistakes": common_mistakes[:6],
            "recap": recap[:8],
        }
