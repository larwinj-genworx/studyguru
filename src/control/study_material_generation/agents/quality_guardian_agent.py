from __future__ import annotations

import ast
import json
import re
from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class QualityGuardianAgent(BaseStructuredAgent):
    _BLOCKING_LLM_KEYWORDS = (
        "unsupported",
        "incorrect",
        "inaccurate",
        "wrong",
        "contradict",
        "topic drift",
        "off-topic",
        "factual",
        "hallucinat",
    )
    _STEPWISE_EXAMPLE_ISSUE = "Practical examples need worked derivations or calculations for this concept."
    _QUANTITATIVE_KEYWORDS = (
        "equation",
        "formula",
        "derive",
        "derivation",
        "algebra",
        "calculus",
        "geometry",
        "trigonometry",
        "physics",
        "chemistry",
        "stoichiometry",
        "kinematic",
        "force",
        "voltage",
        "current",
        "momentum",
        "mole",
        "concentration",
        "probability",
        "statistics",
        "numerical",
        "quantitative",
    )
    _STEPWISE_SIGNAL_KEYWORDS = (
        "substitute",
        "simplify",
        "solve",
        "calculate",
        "derive",
        "rearrange",
        "therefore",
        "hence",
        "units",
        "step",
        "=",
        "+",
        "/",
    )

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="QualityGuardianAgent",
            goal="Validate clarity, completeness, factual grounding, and student-friendliness.",
            backstory="Instructional quality reviewer for school study material.",
        )

    def execute(
        self,
        *,
        concept_name: str,
        content: dict[str, Any],
        resource_required: bool = True,
        evidence_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        blocking_issues: list[str] = []
        advisory_issues: list[str] = []
        definition_word_count = len(str(content.get("definition", "")).split())
        if definition_word_count < 55:
            advisory_issues.append("Definition is too short.")
        if definition_word_count > 150:
            advisory_issues.append("Definition is too long.")
        practical_required = bool(content.get("practical_examples_required", True))
        if practical_required and len(content.get("examples", [])) < 3:
            blocking_issues.append("Need at least 3 practical examples.")
        if practical_required and self._requires_stepwise_examples(concept_name, content):
            if not self._has_enough_stepwise_examples(content.get("examples", [])):
                blocking_issues.append(self._STEPWISE_EXAMPLE_ISSUE)
        if len(content.get("mcqs", [])) < 6:
            blocking_issues.append("Need at least 6 MCQs.")
        if len(content.get("flashcards", [])) < 8:
            blocking_issues.append("Need at least 8 flashcards.")
        if resource_required and len(content.get("references", [])) < 1:
            blocking_issues.append("Need at least one validated reference.")

        source_documents = evidence_pack.get("source_documents", []) if isinstance(evidence_pack, dict) else []
        evidence_snippets = evidence_pack.get("evidence_snippets", []) if isinstance(evidence_pack, dict) else []
        retrieval_status = str(evidence_pack.get("retrieval_status", "")).strip() if isinstance(evidence_pack, dict) else ""
        if resource_required and len(source_documents) < 2:
            target_bucket = blocking_issues if retrieval_status == "grounded" else advisory_issues
            target_bucket.append("Need broader evidence coverage from multiple sources.")
        if resource_required and not evidence_snippets:
            target_bucket = blocking_issues if retrieval_status == "grounded" else advisory_issues
            target_bucket.append("Need grounded evidence snippets for factual support.")

        evidence_text = self.format_evidence_pack(
            evidence_pack,
            max_sources=4,
            max_snippets=6,
            max_chars_per_snippet=220,
        )
        llm_issues: list[str] = []
        llm_guidance: list[str] = []
        try:
            llm_review = self.run_json_task(
                (
                    f"Concept: {concept_name}\n"
                    f"Content Draft: {content}\n"
                    f"Evidence Pack:\n{evidence_text}\n\n"
                    "Review the draft for factual grounding, topic drift, grade appropriateness, and unsupported claims. "
                    "If evidence is limited, allow cautious explanatory wording, but flag statements that look stronger than the evidence. "
                    "Return JSON with keys: approved (boolean), issues (list), guidance (list). "
                    "Output JSON only without markdown fences."
                ),
                required_keys=["approved", "issues", "guidance"],
            )
            llm_issues = self.to_list(llm_review.get("issues"), [])
            llm_guidance = self.to_list(llm_review.get("guidance"), [])
        except Exception as exc:
            llm_guidance.append(f"Evidence review fallback used due to reviewer failure: {exc}")

        for issue in llm_issues:
            normalized_issue = issue.strip()
            if not normalized_issue:
                continue
            if self._is_blocking_llm_issue(normalized_issue):
                if normalized_issue not in blocking_issues:
                    blocking_issues.append(normalized_issue)
            elif normalized_issue not in advisory_issues:
                advisory_issues.append(normalized_issue)

        guidance = []
        guidance_map = {
            "Definition is too short.": "Expand the definition with context, scope, and one practical use case.",
            "Definition is too long.": "Trim the definition to the core idea and remove repetition.",
            "Need at least 3 practical examples.": "Add worked examples that show step-by-step reasoning.",
            self._STEPWISE_EXAMPLE_ISSUE: "Replace story-only examples with derivations, substitutions, or numerical steps that match the concept formulas.",
            "Need at least 6 MCQs.": "Add more MCQs that test concept understanding and application.",
            "Need at least 8 flashcards.": "Add recall flashcards covering terms, steps, and pitfalls.",
            "Need at least one validated reference.": "Add at least one reputable learning resource link.",
            "Need broader evidence coverage from multiple sources.": "Retrieve and use at least two strong external sources before finalizing.",
            "Need grounded evidence snippets for factual support.": "Collect stronger source snippets and align the draft to those passages.",
        }
        for issue in [*blocking_issues, *advisory_issues]:
            guidance.append(guidance_map.get(issue, "Strengthen clarity, completeness, and factual grounding for this concept."))
        for item in llm_guidance:
            if item not in guidance:
                guidance.append(item)
        if not guidance and (blocking_issues or advisory_issues):
            guidance = ["Simplify language, strengthen examples, and add clearer evidence-backed support."]

        approved = not blocking_issues

        return {
            "approved": approved,
            "issues": [*blocking_issues, *advisory_issues][:10],
            "blocking_issues": blocking_issues[:10],
            "advisory_issues": advisory_issues[:10],
            "guidance": guidance[:10],
        }

    @classmethod
    def _is_blocking_llm_issue(cls, issue: str) -> bool:
        normalized = issue.strip().lower()
        if not normalized:
            return False
        return any(keyword in normalized for keyword in cls._BLOCKING_LLM_KEYWORDS)

    @classmethod
    def _requires_stepwise_examples(cls, concept_name: str, content: dict[str, Any]) -> bool:
        formulas = content.get("formulas") or []
        if isinstance(formulas, list) and any(str(item).strip() for item in formulas):
            return True
        text = " ".join(
            [
                concept_name,
                str(content.get("definition", "")),
                " ".join(str(item) for item in content.get("key_steps", []) or []),
                " ".join(str(item) for item in formulas if str(item).strip()),
            ]
        ).lower()
        return any(keyword in text for keyword in cls._QUANTITATIVE_KEYWORDS)

    @classmethod
    def _has_enough_stepwise_examples(cls, examples: Any) -> bool:
        if not isinstance(examples, list) or not examples:
            return False
        signal_count = 0
        target = min(3, len(examples))
        for example in examples:
            example_text = cls._example_to_text(example).lower()
            if not example_text:
                continue
            has_signal = any(keyword in example_text for keyword in cls._STEPWISE_SIGNAL_KEYWORDS)
            if has_signal or any(char.isdigit() for char in example_text):
                signal_count += 1
            if signal_count >= target:
                return True
        return False

    @classmethod
    def _example_to_text(cls, example: Any) -> str:
        if isinstance(example, dict):
            pieces = [
                str(example.get("title", "")),
                str(example.get("prompt", "")),
                str(example.get("result", "")),
            ]
            pieces.extend(str(item) for item in example.get("steps", []) or [])
            return " ".join(piece.strip() for piece in pieces if piece and piece.strip()).strip()
        if isinstance(example, str):
            text = example.strip()
            if not text:
                return ""
            parsed = cls._parse_structured_text(text)
            if parsed is not None:
                return cls._example_to_text(parsed)
            return re.sub(r"\s+", " ", text).strip()
        return str(example).strip()

    @staticmethod
    def _parse_structured_text(raw_text: str) -> Any | None:
        text = raw_text.strip()
        if not text or not (text.startswith("{") or text.startswith("[")):
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        try:
            return ast.literal_eval(text)
        except Exception:
            return None
