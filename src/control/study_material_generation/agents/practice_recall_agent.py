from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings
from src.core.services import flashcard_service


class PracticeRecallAgent(BaseStructuredAgent):
    """Generate concept-aligned recall practice with bounded, complexity-aware volume."""

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
        target_mcq_count = self._determine_target_mcq_count(
            definition=definition,
            key_steps=key_steps,
            common_mistakes=common_mistakes,
            recap=recap,
            formulas=formulas,
            examples=examples,
        )
        flashcard_range = self._determine_flashcard_range(
            target_mcq_count=target_mcq_count,
            key_steps=key_steps,
            formulas=formulas,
        )
        prompt = (
            "You are the practice-and-recall stage in a production learning-content pipeline.\n"
            "Your job is to create a compact but effective set of practice items that students actually expect after studying a concept: enough to reinforce understanding, but not so many that practice becomes noisy or repetitive.\n\n"
            f"Concept: {concept_name}\n"
            f"Definition: {definition}\n"
            f"Intuition: {intuition}\n"
            f"Key Steps: {key_steps}\n"
            f"Common Mistakes: {common_mistakes}\n"
            f"Recap: {recap}\n"
            f"Formulas: {formulas}\n"
            f"Examples: {examples}\n"
            f"Target MCQ Count: {target_mcq_count}\n"
            f"Suggested Flashcard Range: {flashcard_range[0]}-{flashcard_range[1]}\n\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n"
            f"Evidence Pack:\n{evidence_text}\n\n"
            "Return JSON with keys: mcqs, flashcards.\n\n"
            "Volume rules:\n"
            f"- Generate exactly {target_mcq_count} MCQs.\n"
            f"- Generate between {flashcard_range[0]} and {flashcard_range[1]} flashcards.\n"
            "- Do not generate too many MCQs. Keep the set compact, high-value, and non-repetitive.\n"
            "- Only increase MCQ coverage when the concept genuinely has enough depth, misconception risk, or procedural load to justify it.\n\n"
            "MCQ requirements:\n"
            "- Each MCQ must have: question, options, answer, explanation, hints.\n"
            "- options must contain exactly 4 choices.\n"
            "- answer must match one of the options exactly.\n"
            "- explanation must be short, accurate, and helpful to a student reviewing the concept.\n"
            "- hints must contain exactly 3 short progressive hints that guide thinking without revealing the answer directly.\n"
            "- Questions should cover the most important parts of the concept: definition, reasoning, application, common mistakes, and steps when relevant.\n"
            "- Do not make all questions the same type. Mix direct recall, understanding, error-spotting, and application when appropriate.\n"
            "- Avoid trick questions, ambiguous wording, and repetitive rephrasings of the same idea.\n"
            "- Keep language aligned with what a student at this level would reasonably understand.\n\n"
            "Flashcard requirements:\n"
            "- Each flashcard must have: question, hint, answer, kind.\n"
            "- Prioritize the most important facts, definitions, formulas, reasoning points, procedural checkpoints, and common mistakes for this concept.\n"
            "- Write the flashcard question as a short student-facing recall question, not as a label.\n"
            "- Good examples: 'What is Newton's second law?', 'Why does this ratio stay constant?', 'Which step should be checked before simplifying?'.\n"
            "- Avoid vague fronts like 'Core Idea', 'Method', 'Quick Recall', or 'Why It Matters'.\n"
            "- hint must be a brief cue.\n"
            "- answer must be concise, direct, and limited to the exact expected recall point in 1-2 short sentences.\n"
            "- Each flashcard should test one important idea only.\n"
            "- kind must be one of: core, intuition, step, formula, pitfall, summary, practice, concept.\n\n"
            "General quality rules:\n"
            "- Keep all practice items grounded in the evidence pack and aligned with the worked examples.\n"
            "- Strict rule: all questions must test only this concept.\n"
            "- If Revision Feedback is provided, fix those issues first.\n"
            "- Prefer fewer strong questions over many weak or repetitive ones.\n"
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
        if len(mcqs) < target_mcq_count:
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
        if len(flashcards) < flashcard_range[0]:
            raise ValueError("PracticeRecallAgent returned insufficient flashcards.")

        return {"mcqs": mcqs[:target_mcq_count], "flashcards": flashcards[: flashcard_range[1]]}

    @staticmethod
    def _determine_target_mcq_count(
        *,
        definition: str,
        key_steps: list[str],
        common_mistakes: list[str],
        recap: list[str],
        formulas: list[str],
        examples: list[str],
    ) -> int:
        complexity_score = 0
        if len(definition.split()) >= 90:
            complexity_score += 1
        if len(key_steps) >= 3:
            complexity_score += 1
        if len(key_steps) >= 5:
            complexity_score += 1
        if len(common_mistakes) >= 4:
            complexity_score += 1
        if len(formulas) >= 1:
            complexity_score += 1
        if len(formulas) >= 3:
            complexity_score += 1
        if len(examples) >= 4:
            complexity_score += 1
        if len(recap) >= 5:
            complexity_score += 1

        if complexity_score <= 2:
            return 5
        if complexity_score <= 5:
            return 6
        if complexity_score <= 7:
            return 7
        return 8

    @staticmethod
    def _determine_flashcard_range(
        *,
        target_mcq_count: int,
        key_steps: list[str],
        formulas: list[str],
    ) -> tuple[int, int]:
        minimum = max(8, target_mcq_count + 2)
        maximum = minimum + 3
        if len(key_steps) >= 4 or len(formulas) >= 2:
            maximum += 1
        return minimum, min(maximum, 14)
