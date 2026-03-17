from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class StudyMaterialEngineAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="StudyMaterialEngineAgent",
            goal="Generate complete, production-grade study material in one grounded pass.",
            backstory="Senior instructional designer focused on rigorous, evidence-backed study material.",
        )

    def execute(
        self,
        *,
        subject_name: str,
        concept_name: str,
        level: str,
        auto_revision_enabled: bool,
        coverage_map: dict[str, Any],
        teaching_plan: dict[str, Any],
        revision_feedback: str | None,
        evidence_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        auto_flag = "true" if auto_revision_enabled else "false"
        evidence_text = self.format_evidence_pack(
            evidence_pack,
            max_sources=4,
            max_snippets=6,
            max_chars_per_snippet=260,
        )
        prompt = (
            "You are a production-grade study material generation engine inside a grounded LangGraph workflow.\n\n"
            "Your job is to produce complete study material from external evidence, not from unsupported assumptions.\n\n"
            f"Subject: {subject_name}\n"
            f"Concept: {concept_name}\n"
            f"Student Level: {level}\n"
            f"Auto Revision Enabled: {auto_flag}\n"
            f"Coverage Map: {coverage_map}\n"
            f"Teaching Plan: {teaching_plan}\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n"
            f"Evidence Pack:\n{evidence_text}\n\n"
            "Requirements:\n"
            "1. Generate complete, pedagogically sound content for the exact concept given.\n"
            "2. Do not reject uncommon or advanced topics. Teach the exact topic in the simplest grade-appropriate way.\n"
            "3. Use the evidence pack as the factual base. If evidence is thin, use cautious wording and avoid unsupported claims.\n"
            "4. Keep the content concept-specific, non-repetitive, and structured for student learning.\n"
            "5. Include meaningful examples and formulas only when they are relevant and supported.\n"
            "6. Do not force a step-by-step explanation for every concept. Use ordered steps only when the topic genuinely involves a procedure, derivation, workflow, experiment, or multi-step solution path.\n"
            "7. For descriptive or theory-heavy topics, explain clearly in natural paragraphs and concise bullets instead of inventing procedural steps.\n"
            "8. Avoid markdown tables, HTML, or very long unbroken strings that can break downstream rendering.\n"
            "9. If revision feedback exists, fix those issues first.\n\n"
            "Return strict JSON only in this format:\n"
            "{\n"
            '  "concept_analysis": {\n'
            '    "concept_level": "",\n'
            '    "complexity_score": "",\n'
            '    "required_depth": ""\n'
            "  },\n"
            '  "content": {\n'
            '    "full_study_material": "",\n'
            '    "quick_revision": "",\n'
            '    "examples": [],\n'
            '    "formulas": []\n'
            "  },\n"
            '  "quality_metrics": {\n'
            '    "word_count": "",\n'
            '    "sections_complete": true,\n'
            '    "grounded_to_sources": true,\n'
            '    "refinement_used": false\n'
            "  }\n"
            "}\n\n"
            "Output JSON only without markdown fences."
        )
        data = self.run_json_task(
            prompt,
            required_keys=["concept_analysis", "content", "quality_metrics"],
        )

        content = data.get("content") or {}
        full_text = str(content.get("full_study_material", "")).strip()
        quick_revision = str(content.get("quick_revision", "")).strip()
        if not full_text:
            raise ValueError("StudyMaterialEngineAgent returned empty full_study_material.")
        if not quick_revision:
            raise ValueError("StudyMaterialEngineAgent returned empty quick_revision.")

        examples = content.get("examples")
        if not isinstance(examples, list):
            examples = []
        formulas = content.get("formulas")
        if not isinstance(formulas, list):
            formulas = []
        content["examples"] = [str(item).strip() for item in examples if str(item).strip()]
        content["formulas"] = [str(item).strip() for item in formulas if str(item).strip()]
        data["content"] = content
        data["grounding"] = self.build_grounding_metadata(evidence_pack)
        return data
