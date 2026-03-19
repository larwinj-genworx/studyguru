from __future__ import annotations

from typing import Any

from src.config.settings import Settings
from src.control.study_material_generation.agents.base import BaseStructuredAgent


class LearningBotResponseAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="LearningBotResponseAgent",
            goal="Answer student doubts using grounded concept evidence only.",
            backstory=(
                "A patient concept tutor who explains clearly, stays inside the current topic, "
                "and only uses retrieved evidence."
            ),
            temperature=0.15,
        )

    def execute(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        response_mode: str,
        student_message: str,
        recent_history: list[dict[str, str]],
        evidence_blocks: list[dict[str, str]],
    ) -> dict[str, Any]:
        history_lines = [
            f"{item.get('role', 'user').title()}: {item.get('content', '').strip()}"
            for item in recent_history
            if item.get("content")
        ]
        evidence_lines = []
        for block in evidence_blocks:
            evidence_lines.append(
                (
                    f"[{block.get('source_id')}] type={block.get('source_type')} "
                    f"label={block.get('label')} note={block.get('note') or 'n/a'}\n"
                    f"Text: {block.get('text')}"
                )
            )

        prompt = (
            f"Subject: {subject_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Concept Name: {concept_name}\n"
            f"Concept Description: {concept_description or 'None'}\n"
            f"Response Mode: {response_mode}\n"
            f"Student Message: {student_message.strip()}\n\n"
            "Recent Conversation:\n"
            f"{chr(10).join(history_lines) if history_lines else 'No prior conversation.'}\n\n"
            "Grounded Evidence:\n"
            f"{chr(10).join(evidence_lines) if evidence_lines else 'No evidence retrieved.'}\n\n"
            "Task:\n"
            "- Answer the student clearly and in a teaching-friendly manner.\n"
            "- Stay focused on the current concept unless the student explicitly asks for a comparison.\n"
            "- Use only the grounded evidence above for factual claims.\n"
            "- If evidence is partial, say that directly instead of guessing.\n"
            "- If response mode is practice, include 2 or 3 short practice questions.\n"
            "- If response mode is step_by_step, explain in ordered steps.\n"
            "- Keep the answer concise but useful.\n\n"
            "Return JSON only with keys:\n"
            "- answer: string\n"
            "- used_source_ids: array of source ids you relied on\n"
            "- follow_up_suggestions: array with exactly 3 short follow-up prompts\n"
            "- confidence: one of high, medium, low"
        )
        return self.run_json_task(
            prompt,
            required_keys=["answer", "used_source_ids", "follow_up_suggestions", "confidence"],
        )
