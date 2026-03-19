from __future__ import annotations

import re
from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class ConceptExplainerAgent(BaseStructuredAgent):
    _STEP_ACTION_PREFIXES = (
        "identify",
        "determine",
        "find",
        "check",
        "rewrite",
        "substitute",
        "simplify",
        "solve",
        "calculate",
        "compare",
        "draw",
        "label",
        "plot",
        "arrange",
        "classify",
        "verify",
        "apply",
        "use",
        "start",
        "first",
        "next",
        "then",
        "finally",
    )

    _GENERIC_STUDY_PREFIXES = (
        "understand",
        "learn",
        "remember",
        "revise",
        "practice",
        "study",
        "read",
        "know",
        "be aware",
    )

    _PROCEDURAL_SIGNAL_KEYWORDS = (
        "step",
        "procedure",
        "process",
        "workflow",
        "algorithm",
        "method",
        "derive",
        "derivation",
        "calculation",
        "compute",
        "solve",
        "construct",
        "experiment",
        "measurement",
        "proof",
    )

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
        evidence_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence_text = self.format_evidence_pack(
            evidence_pack,
            max_sources=4,
            max_snippets=6,
            max_chars_per_snippet=240,
        )
        prompt = (
            f"Concept: {concept_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Coverage: {coverage_map}\n"
            f"Teaching Plan: {teaching_plan}\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n"
            f"Evidence Pack:\n{evidence_text}\n\n"
            "Return JSON with keys: definition (string), intuition (string), formulas (list), "
            "stepwise_breakdown_required (boolean), key_steps (list), common_mistakes (list), recap (list), "
            "practical_examples_required (boolean). "
            "Definition should be 70-110 words. Intuition should be 3-5 short sentences. "
            "Provide 4-6 common_mistakes and 4-6 recap bullets. "
            "Formulas: include only if the concept truly uses equations/formulae; otherwise return an empty list. "
            "Always include the key_steps field in the JSON response. Use an empty list when no stepwise section is needed. "
            "Set stepwise_breakdown_required to true only when the concept genuinely needs an ordered process, derivation, workflow, proof sequence, experiment sequence, or multi-step solving method. "
            "If stepwise_breakdown_required is true, provide 3-6 short action-oriented key_steps. "
            "If the topic is mostly descriptive, definitional, conceptual, or theory-based, set stepwise_breakdown_required to false and return key_steps as an empty list. "
            "Do not force generic study advice or fake procedural steps for non-procedural topics. "
            "Set practical_examples_required to false only when the concept is purely theoretical "
            "and does not lend itself to realistic practical examples. "
            "Use the evidence pack as the factual grounding. If the evidence is thin, keep wording careful and avoid unsupported claims. "
            "Do not reject uncommon topics; instead explain the exact topic in a simplified, grade-appropriate way. "
            "If Revision Feedback is provided, fix those issues first. "
            "Strict rule: explanation must remain fully concept-specific and should not mention unrelated topics. "
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(
            prompt,
            required_keys=[
                "definition",
                "intuition",
                "common_mistakes",
                "recap",
            ],
        )
        definition = str(data.get("definition", "")).strip()
        intuition = str(data.get("intuition", "")).strip()
        formulas = self.to_list(data.get("formulas"), [])
        raw_key_steps = self.to_list(data.get("key_steps"), [])
        common_mistakes = self.to_list(data.get("common_mistakes"), [])
        recap = self.to_list(data.get("recap"), [])
        if not definition or not intuition or not common_mistakes or not recap:
            raise ValueError("ConceptExplainerAgent produced incomplete core notes.")

        def _word_count(text: str) -> int:
            return len(text.split())

        def _limit_words(text: str, max_words: int) -> str:
            words = text.split()
            if len(words) <= max_words:
                return text
            return " ".join(words[:max_words]).strip()

        def _ensure_definition_min_words(
            text: str,
            *,
            min_words: int,
            max_words: int,
            objectives: list[str],
            steps: list[str],
        ) -> str:
            if _word_count(text) >= min_words:
                return text
            additions: list[str] = []
            if objectives:
                trimmed = [obj.strip().rstrip(".") for obj in objectives if obj.strip()]
                if trimmed:
                    additions.append(f"At this level, students should be able to {'; '.join(trimmed[:2])}.")
            if steps:
                lead_step = steps[0].strip().rstrip(".")
                if lead_step:
                    additions.append(
                        f"A typical approach begins by {lead_step.lower()} and then checking the result."
                    )
            additions.append(
                f"For {grade_level} learners, the focus is on understanding {concept_name} clearly and applying it correctly."
            )
            expanded = " ".join([text.strip(), *additions]).strip()
            if _word_count(expanded) < min_words:
                expanded = (
                    f"{expanded} "
                    f"This helps students explain the idea in their own words and use it in routine problems."
                ).strip()
            return _limit_words(expanded, max_words)

        objectives = self.to_list(coverage_map.get("objectives"), [])
        stepwise_breakdown_required, key_steps = self._normalize_key_steps(
            concept_name=concept_name,
            definition=definition,
            raw_key_steps=raw_key_steps,
            formulas=formulas,
            objectives=objectives,
            teaching_plan=teaching_plan,
            requested_flag=data.get("stepwise_breakdown_required"),
        )
        definition = _ensure_definition_min_words(
            definition,
            min_words=70,
            max_words=140,
            objectives=objectives,
            steps=key_steps,
        )
        intuition = _limit_words(intuition, 90)
        formulas = [str(item).strip() for item in formulas if str(item).strip()][:6]
        practical_examples_required = self._to_bool(data.get("practical_examples_required"), default=True)
        return {
            "definition": definition,
            "intuition": intuition,
            "formulas": formulas,
            "stepwise_breakdown_required": stepwise_breakdown_required,
            "key_steps": key_steps[:10],
            "common_mistakes": common_mistakes[:8],
            "recap": recap[:8],
            "practical_examples_required": practical_examples_required,
        }

    def _normalize_key_steps(
        self,
        *,
        concept_name: str,
        definition: str,
        raw_key_steps: list[str],
        formulas: list[str],
        objectives: list[str],
        teaching_plan: dict[str, Any],
        requested_flag: Any,
    ) -> tuple[bool, list[str]]:
        cleaned_steps: list[str] = []
        seen: set[str] = set()
        for step in raw_key_steps:
            cleaned = str(step).strip().strip("-").strip()
            if not cleaned:
                continue
            normalized = " ".join(cleaned.lower().split())
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned_steps.append(cleaned)

        action_steps = [step for step in cleaned_steps if self._looks_like_step(step)]
        requested = self._to_bool(requested_flag, default=False)

        evidence_text = " ".join(
            [
                concept_name,
                definition,
                " ".join(formulas),
                " ".join(objectives),
                " ".join(self.to_list(teaching_plan.get("lesson_flow"), [])),
                " ".join(self.to_list(teaching_plan.get("teaching_tips"), [])),
            ]
        ).lower()
        procedural_signal_present = any(keyword in evidence_text for keyword in self._PROCEDURAL_SIGNAL_KEYWORDS)
        if len(action_steps) < 2:
            return False, []

        should_keep_steps = requested or procedural_signal_present

        if not should_keep_steps:
            return False, []

        return bool(action_steps), action_steps[:6]

    def _looks_like_step(self, value: str) -> bool:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            return False
        lowered = cleaned.lower()
        if len(cleaned.split()) < 3:
            return False
        if any(lowered.startswith(prefix) for prefix in self._GENERIC_STUDY_PREFIXES):
            return False
        if any(lowered.startswith(prefix) for prefix in self._STEP_ACTION_PREFIXES):
            return True
        if re.match(r"^(step\s+\d+|first|next|then|finally)\b", lowered):
            return True
        return False

    @staticmethod
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
