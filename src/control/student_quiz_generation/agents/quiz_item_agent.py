from __future__ import annotations

from typing import Any

from src.config.settings import Settings
from src.control.study_material_generation.agents.base import BaseStructuredAgent


class QuizItemAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="StudentQuizItemAgent",
            goal="Generate high-quality MCQs with progressive hints.",
            backstory="Assessment designer who builds rigorous concept-aligned quizzes.",
        )

    def execute(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_summary: str,
        key_points: list[str],
        common_mistakes: list[str],
        question_count: int,
        revision_feedback: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        prompt = (
            f"Subject: {subject_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Concept: {concept_name}\n"
            f"Concept Summary: {concept_summary}\n"
            f"Key Points: {key_points}\n"
            f"Common Mistakes: {common_mistakes}\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n\n"
            "Task: Generate a concept-focused quiz.\n"
            "Return JSON with key: mcqs (exactly the requested count).\n"
            f"Requested Count: {question_count}\n\n"
            "Each MCQ must include:\n"
            "- question (clear, single-best answer)\n"
            "- options (exactly 4 options)\n"
            "- answer (must match one of the options exactly)\n"
            "- explanation (brief but precise)\n"
            "- difficulty (easy, medium, or hard)\n"
            "- hints (exactly 3 progressive hints)\n\n"
            "Hint rules:\n"
            "- Hint 1: general guidance\n"
            "- Hint 2: more specific direction\n"
            "- Hint 3: nearly-sufficient clue but NEVER reveals the exact answer text\n"
            "- No hint should contain the exact answer option text\n\n"
            "Constraints:\n"
            "- All questions must be strictly about the given concept\n"
            "- Avoid ambiguous or multi-correct questions\n"
            "- Avoid trick questions\n"
            "- Keep language appropriate for the grade level\n"
            "- Output JSON only without markdown fences"
        )
        return self.run_json_task(prompt, required_keys=["mcqs"])
