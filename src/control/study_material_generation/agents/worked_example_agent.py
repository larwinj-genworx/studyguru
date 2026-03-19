from __future__ import annotations

import ast
import json
import re
from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class WorkedExampleAgent(BaseStructuredAgent):
    _DERIVATION_KEYWORDS = (
        "derive",
        "derivation",
        "proof",
        "prove",
        "identity",
        "rearrange",
        "simplify",
        "equation",
        "formula",
        "stoichiometry",
        "balancing",
        "kinematic",
        "motion",
        "circuit",
        "current",
        "voltage",
        "force",
        "momentum",
        "acceleration",
        "wave",
        "mole",
        "molar",
        "concentration",
        "trigonometry",
        "calculus",
        "algebra",
        "geometry",
        "probability",
        "statistics",
    )
    _QUANTITATIVE_SUBJECT_KEYWORDS = (
        "math",
        "maths",
        "mathematics",
        "physics",
        "chemistry",
        "statistic",
        "quantitative",
        "numerical",
        "accounting",
        "economics",
    )
    _STEPWISE_SIGNALS = (
        "substitute",
        "calculate",
        "solve",
        "simplify",
        "rearrange",
        "derive",
        "therefore",
        "hence",
        "units",
        "=",
        "+",
        "/",
    )

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="WorkedExampleAgent",
            goal="Generate practical worked examples with increasing difficulty.",
            backstory="Practice designer who converts concepts into solvable examples.",
            enable_json_mode=False,
        )

    def execute(
        self,
        *,
        subject_name: str,
        concept_name: str,
        grade_level: str,
        key_steps: list[str],
        formulas: list[str] | None,
        revision_feedback: str | None,
        practical_examples_required: bool = True,
        evidence_pack: dict | None = None,
    ) -> dict[str, list[str]]:
        if not practical_examples_required:
            return {"examples": []}

        cleaned_formulas = [str(item).strip() for item in (formulas or []) if str(item).strip()][:6]
        preferred_style = self._infer_example_style(
            subject_name=subject_name,
            concept_name=concept_name,
            key_steps=key_steps,
            formulas=cleaned_formulas,
            revision_feedback=revision_feedback,
        )
        evidence_text = self.format_evidence_pack(
            evidence_pack,
            max_sources=4,
            max_snippets=5,
            max_chars_per_snippet=220,
        )
        prompt = (
            f"Subject: {subject_name}\n"
            f"Concept: {concept_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Key Steps: {key_steps}\n"
            f"Formula Signals: {cleaned_formulas}\n"
            f"Preferred Example Style: {preferred_style}\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n"
            f"Evidence Pack:\n{evidence_text}\n\n"
            "Return JSON with key: examples (list). Each example must be an object with keys: "
            "title (string), prompt (string), steps (list of 3-6 short strings), result (string), "
            "example_type (string). "
            "Include 4 to 6 worked examples with increasing difficulty. "
            "Strict rule: every example must stay fully inside this concept only. "
            "Use plain text equations only; do not use markdown tables, LaTeX, or HTML. "
            f"{self._style_instruction(preferred_style)} "
            "Base the examples on the evidence pack and keep formulas, units, and reasoning consistent. "
            "If Revision Feedback is provided, fix those issues first. "
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(prompt, required_keys=["examples"])
        examples = self._normalize_examples(
            data.get("examples"),
            preferred_style=preferred_style,
            concept_name=concept_name,
            key_steps=key_steps,
            formulas=cleaned_formulas,
        )
        if len(examples) < 4:
            examples.extend(
                self._fallback_examples(
                    preferred_style=preferred_style,
                    concept_name=concept_name,
                    key_steps=key_steps,
                    formulas=cleaned_formulas,
                    existing=len(examples),
                )
            )
        if len(examples) < 4:
            raise ValueError("WorkedExampleAgent returned insufficient examples.")
        return {"examples": examples[:6]}

    @classmethod
    def _infer_example_style(
        cls,
        *,
        subject_name: str,
        concept_name: str,
        key_steps: list[str],
        formulas: list[str],
        revision_feedback: str | None,
    ) -> str:
        haystack = " ".join(
            [
                subject_name,
                concept_name,
                " ".join(key_steps or []),
                " ".join(formulas or []),
                revision_feedback or "",
            ]
        ).lower()
        if any(keyword in haystack for keyword in cls._DERIVATION_KEYWORDS):
            return "derivation"
        if formulas:
            return "calculation"
        if any(keyword in haystack for keyword in cls._QUANTITATIVE_SUBJECT_KEYWORDS):
            return "calculation"
        return "scenario"

    @staticmethod
    def _style_instruction(preferred_style: str) -> str:
        if preferred_style == "derivation":
            return (
                "For this concept, examples must be derivation-first. Do not produce generic day-to-day story scenarios. "
                "Show symbolic manipulation, justified transformations, and a final derived expression or verified result. "
                "At least 3 examples must be derivations or proof-like worked solutions."
            )
        if preferred_style == "calculation":
            return (
                "For this concept, examples must be worked calculations. Avoid story-only scenarios. "
                "Show the known values, selected relation, substitution, simplification, units when relevant, and final answer. "
                "At least 3 examples must be numerical or equation-based worked solutions."
            )
        return (
            "For this concept, examples may use realistic classroom or daily-life scenarios, but each one must still show a clear worked solution."
        )

    def _normalize_examples(
        self,
        raw_examples: Any,
        *,
        preferred_style: str,
        concept_name: str,
        key_steps: list[str],
        formulas: list[str],
    ) -> list[str]:
        if not isinstance(raw_examples, list):
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for index, item in enumerate(raw_examples, start=1):
            payload = self._normalize_single_example(
                item,
                index=index,
                preferred_style=preferred_style,
                concept_name=concept_name,
                key_steps=key_steps,
                formulas=formulas,
            )
            if not payload:
                continue
            serialized = json.dumps(payload, ensure_ascii=True)
            signature = re.sub(r"\s+", " ", serialized.lower()).strip()
            if signature in seen:
                continue
            seen.add(signature)
            normalized.append(serialized)
        return normalized

    def _normalize_single_example(
        self,
        item: Any,
        *,
        index: int,
        preferred_style: str,
        concept_name: str,
        key_steps: list[str],
        formulas: list[str],
    ) -> dict[str, Any] | None:
        parsed = self._parse_example_item(item)
        if not parsed:
            return None

        title = parsed.get("title", "").strip()
        prompt = parsed.get("prompt", "").strip()
        result = parsed.get("result", "").strip()
        example_type = parsed.get("example_type", "").strip().lower() or preferred_style
        raw_steps = parsed.get("steps") or []
        steps = [self._clean_step_text(step) for step in raw_steps if self._clean_step_text(step)]

        if not steps:
            steps = self._fallback_steps(
                preferred_style=preferred_style,
                concept_name=concept_name,
                key_steps=key_steps,
                formulas=formulas,
            )

        if preferred_style != "scenario" and not self._has_stepwise_signal(steps):
            steps = [*steps[:1], *self._fallback_steps(preferred_style=preferred_style, concept_name=concept_name, key_steps=key_steps, formulas=formulas)]
            steps = self._dedupe_steps(steps)[:6]

        if not title:
            title = self._default_title(preferred_style, index)
        if not prompt:
            prompt = self._default_prompt(preferred_style, concept_name, formulas, index)
        if not result:
            result = self._default_result(preferred_style)

        payload = {
            "title": title,
            "prompt": prompt,
            "steps": self._dedupe_steps(steps)[:6],
            "result": result,
            "example_type": example_type,
        }
        if len(payload["steps"]) < 3:
            return None
        return payload

    def _parse_example_item(self, item: Any) -> dict[str, Any] | None:
        if isinstance(item, dict):
            return {
                "title": str(item.get("title") or item.get("example") or "").strip(),
                "prompt": str(
                    item.get("prompt")
                    or item.get("question")
                    or item.get("problem")
                    or item.get("description")
                    or item.get("context")
                    or ""
                ).strip(),
                "steps": self._coerce_steps(
                    item.get("steps")
                    or item.get("stepwise_solution")
                    or item.get("solution")
                    or item.get("working")
                    or item.get("process")
                    or item.get("method")
                ),
                "result": str(item.get("result") or item.get("answer") or item.get("final_answer") or "").strip(),
                "example_type": str(item.get("example_type") or item.get("type") or item.get("style") or "").strip(),
            }
        if isinstance(item, str):
            text = item.strip()
            if not text:
                return None
            structured = self._parse_structured_text(text)
            if isinstance(structured, dict):
                return self._parse_example_item(structured)
            if isinstance(structured, list):
                return {"title": "", "prompt": "", "steps": self._coerce_steps(structured), "result": "", "example_type": ""}

            title = ""
            prompt = ""
            body = text
            title_match = re.match(r"^(?:example\s*\d+\s*[:\-]\s*)?([^:]{6,120})\s*:\s*(.+)$", text, flags=re.I)
            if title_match:
                title = title_match.group(1).strip()
                body = title_match.group(2).strip()
            steps = self._coerce_steps(body)
            if steps:
                prompt = steps[0] if len(steps) == 1 else ""
            return {
                "title": title,
                "prompt": prompt,
                "steps": steps,
                "result": "",
                "example_type": "",
            }
        return None

    @staticmethod
    def _parse_structured_text(raw_text: str) -> Any | None:
        text = raw_text.strip()
        if not text or not (text.startswith("{") or text.startswith("[")):
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        try:
            return ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return None

    @staticmethod
    def _coerce_steps(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) > 1:
                return lines
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+|(?<=\))\s+|(?<=:)\s+", text)
                if sentence.strip()
            ]
            if len(sentences) > 1:
                return sentences
            parts = [part.strip() for part in re.split(r"\s*;\s*", text) if part.strip()]
            return parts or [text]
        return []

    @staticmethod
    def _clean_step_text(step: str) -> str:
        return (
            str(step)
            .strip()
            .replace("\n", " ")
            .replace("\r", " ")
            .strip(" -")
            .strip()
        )

    @classmethod
    def _has_stepwise_signal(cls, steps: list[str]) -> bool:
        text = " ".join(steps).lower()
        if any(signal in text for signal in cls._STEPWISE_SIGNALS):
            return True
        return any(char.isdigit() for char in text)

    @staticmethod
    def _dedupe_steps(steps: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for step in steps:
            text = str(step).strip()
            if not text:
                continue
            normalized = re.sub(r"\s+", " ", text.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(text)
        return cleaned

    @staticmethod
    def _default_title(preferred_style: str, index: int) -> str:
        label_map = {
            "derivation": "Worked Derivation",
            "calculation": "Worked Calculation",
            "scenario": "Worked Example",
        }
        return f"{label_map.get(preferred_style, 'Worked Example')} {index}"

    @staticmethod
    def _default_prompt(preferred_style: str, concept_name: str, formulas: list[str], index: int) -> str:
        formula_hint = formulas[min(index - 1, len(formulas) - 1)] if formulas else ""
        if preferred_style == "derivation":
            if formula_hint:
                return f"Derive or justify a result for {concept_name} starting from {formula_hint}."
            return f"Derive a correct relation or simplified result for {concept_name}."
        if preferred_style == "calculation":
            if formula_hint:
                return f"Solve a {concept_name} problem using {formula_hint}."
            return f"Solve a step-by-step problem on {concept_name}."
        return f"Apply {concept_name} in a clear practical situation and solve it step by step."

    @staticmethod
    def _default_result(preferred_style: str) -> str:
        if preferred_style == "derivation":
            return "A correct final derived expression or verified relationship."
        if preferred_style == "calculation":
            return "A verified final answer with the correct value or unit."
        return "A correct conclusion that matches the concept."

    def _fallback_steps(
        self,
        *,
        preferred_style: str,
        concept_name: str,
        key_steps: list[str],
        formulas: list[str],
    ) -> list[str]:
        formula_hint = formulas[0] if formulas else ""
        core_step = key_steps[0].strip() if key_steps else f"identify the main rule behind {concept_name}"
        if preferred_style == "derivation":
            steps = [
                f"Start from the governing relation for {concept_name}{f': {formula_hint}' if formula_hint else ''}.",
                "Rearrange one term at a time and state why each algebraic step is valid.",
                f"Use the concept rule to {core_step.lower().rstrip('.')}.",
                "Simplify the expression carefully and check that the final form is consistent.",
            ]
        elif preferred_style == "calculation":
            steps = [
                f"Identify the known quantities and target quantity in the {concept_name} problem.",
                f"Choose the correct relation{f' ({formula_hint})' if formula_hint else ''} before substituting values.",
                "Substitute the values carefully, keeping symbols and units aligned.",
                "Simplify the calculation step by step and verify that the result is reasonable.",
            ]
        else:
            steps = [
                f"Understand the practical situation where {concept_name} is being used.",
                f"Apply the main rule by first {core_step.lower().rstrip('.')}.",
                "Work through the reasoning in order without skipping intermediate steps.",
                "State the final conclusion and briefly verify it.",
            ]
        return self._dedupe_steps(steps)

    def _fallback_examples(
        self,
        *,
        preferred_style: str,
        concept_name: str,
        key_steps: list[str],
        formulas: list[str],
        existing: int,
    ) -> list[str]:
        examples: list[str] = []
        for index in range(existing + 1, 5):
            payload = {
                "title": self._default_title(preferred_style, index),
                "prompt": self._default_prompt(preferred_style, concept_name, formulas, index),
                "steps": self._fallback_steps(
                    preferred_style=preferred_style,
                    concept_name=concept_name,
                    key_steps=key_steps,
                    formulas=formulas,
                ),
                "result": self._default_result(preferred_style),
                "example_type": preferred_style,
            }
            examples.append(json.dumps(payload, ensure_ascii=True))
        return examples
