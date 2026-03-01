from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class PracticeRecallAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="PracticeAndRecallAgent",
            goal="Create MCQs and flashcards for active recall and confidence.",
            backstory="Assessment expert who builds concise formative practice.",
        )

    def execute(
        self,
        *,
        concept_name: str,
        definition: str,
        examples: list[str],
        revision_feedback: str | None,
    ) -> dict[str, list[dict[str, Any]]]:
        prompt = (
            f"Concept: {concept_name}\n"
            f"Definition: {definition}\n"
            f"Examples: {examples}\n\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n\n"
            "Return JSON with keys: mcqs (6-10 items), flashcards (8-15 items). "
            "Each MCQ should have question, options (exactly 4), answer (one of the options), explanation. "
            "Each flashcard should have question and answer. "
            "If Revision Feedback is provided, fix those issues first. "
            "Strict rule: all questions must test only this concept. "
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(
            prompt,
            required_keys=["mcqs", "flashcards"],
        )

        mcqs: list[dict[str, Any]] = []
        for item in data.get("mcqs", []):
            if not isinstance(item, dict):
                continue
            options = [str(opt).strip() for opt in item.get("options", []) if str(opt).strip()]
            if len(options) != 4:
                continue
            question = str(item.get("question", "")).strip()
            explanation = str(item.get("explanation", "")).strip()
            answer = str(item.get("answer", "")).strip()
            if not question or not answer or not explanation:
                continue
            mcqs.append(
                {
                    "question": question,
                    "options": options[:4],
                    "answer": answer,
                    "explanation": explanation,
                }
            )
        if len(mcqs) < 6:
            raise ValueError("PracticeRecallAgent returned insufficient valid MCQs.")

        flashcards: list[dict[str, str]] = []
        for item in data.get("flashcards", []):
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            if question and answer:
                flashcards.append({"question": question, "answer": answer})
        if len(flashcards) < 8:
            raise ValueError("PracticeRecallAgent returned insufficient flashcards.")

        return {"mcqs": mcqs[:10], "flashcards": flashcards[:15]}
