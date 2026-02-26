from __future__ import annotations

from .base import BaseStructuredAgent
from ..config import Settings


class WorkedExampleAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="WorkedExampleAgent",
            goal="Generate practical worked examples with increasing difficulty.",
            backstory="Practice designer who converts concepts into solvable examples.",
        )

    def execute(self, *, concept_name: str, key_steps: list[str], revision_feedback: str | None) -> dict[str, list[str]]:
        prompt = (
            f"Concept: {concept_name}\n"
            f"Key Steps: {key_steps}\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n\n"
            "Return JSON with key: examples (list). Include 3 to 5 short solved examples (1-3 sentences each). "
            "If Revision Feedback is provided, fix those issues first. "
            "Strict rule: each example must explicitly belong to this concept only. "
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(prompt, required_keys=["examples"])
        examples = self.to_list(data.get("examples"), [])
        if len(examples) < 3:
            raise ValueError("WorkedExampleAgent returned insufficient examples.")
        return {"examples": examples[:5]}
