from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings
from src.core.services import flashcard_service


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
        intuition: str,
        key_steps: list[str],
        common_mistakes: list[str],
        recap: list[str],
        formulas: list[str],
        examples: list[str],
        revision_feedback: str | None,
        evidence_pack: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        evidence_text = self.format_evidence_pack(
            evidence_pack,
            max_sources=4,
            max_snippets=5,
            max_chars_per_snippet=220,
        )
        prompt = (
            f"Concept: {concept_name}\n"
            f"Definition: {definition}\n"
            f"Intuition: {intuition}\n"
            f"Key Steps: {key_steps}\n"
            f"Common Mistakes: {common_mistakes}\n"
            f"Recap: {recap}\n"
            f"Formulas: {formulas}\n"
            f"Examples: {examples}\n\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n"
            f"Evidence Pack:\n{evidence_text}\n\n"
            "Return JSON with keys: mcqs (6-10 items), flashcards (8-15 items). "
            "Each MCQ should have question, options (exactly 4), answer (one of the options), explanation, "
            "and hints (exactly 3 short hints that do not reveal the answer directly). "
            "Each flashcard should have question, hint, answer, and kind. "
            "For flashcards, question must be a short heading only, ideally 1-4 words naming the exact term, formula name, law, rule, step, or pitfall. "
            "Do not write flashcard questions as full questions like 'What is...' or 'Why is...'. "
            "Hint must be a very brief abstract cue for the front side. "
            "Answer must reveal the exact concept, relation, step, or pitfall in 1-3 concise sentences. "
            "kind must be one of: core, intuition, step, formula, pitfall, summary, practice, concept. "
            "Keep the practice items grounded in the evidence pack and aligned with the worked examples. "
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
            hints = [str(hint).strip() for hint in item.get("hints", []) if str(hint).strip()]
            mcqs.append(
                {
                    "question": question,
                    "options": options[:4],
                    "answer": answer,
                    "explanation": explanation,
                    "hints": hints[:3],
                }
            )
        if len(mcqs) < 6:
            raise ValueError("PracticeRecallAgent returned insufficient valid MCQs.")

        flashcards = flashcard_service.build_flashcards(
            concept_name=concept_name,
            definition=definition,
            intuition=intuition,
            key_steps=key_steps,
            common_mistakes=common_mistakes,
            recap=recap,
            formulas=formulas,
            raw_flashcards=[item for item in data.get("flashcards", []) if isinstance(item, dict)],
        )
        if len(flashcards) < 8:
            raise ValueError("PracticeRecallAgent returned insufficient flashcards.")

        return {"mcqs": mcqs[:10], "flashcards": flashcards[:15]}
