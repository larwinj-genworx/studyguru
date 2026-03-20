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
            "You are the core study material generation engine in a production educational content pipeline.\n"
            "Your responsibility is to produce accurate, teachable, concept-specific study material that downstream agents can refine into explanations, formulas, examples, recall practice, and final artifacts.\n\n"
            f"Subject: {subject_name}\n"
            f"Concept: {concept_name}\n"
            f"Student Level: {level}\n"
            f"Auto Revision Enabled: {auto_flag}\n"
            f"Coverage Map: {coverage_map}\n"
            f"Teaching Plan: {teaching_plan}\n"
            f"Revision Feedback: {revision_feedback or 'None'}\n"
            f"Evidence Pack:\n{evidence_text}\n\n"
            "Primary objectives:\n"
            "1. Generate complete, instruction-ready material for this exact concept only.\n"
            "2. Keep the material factually grounded in the evidence pack and aligned with the coverage map and teaching plan.\n"
            "3. Make the explanation usable for the stated level without becoming shallow, vague, or generic.\n"
            "4. Produce content in a professional educational style suitable for a real learning platform.\n\n"
            "Strict content rules:\n"
            "1. Stay tightly scoped to the exact concept. Do not drift into broad chapter summaries, unrelated theory, or neighboring topics unless they are essential for understanding this concept.\n"
            "2. Use the evidence pack as the factual anchor. If evidence is limited, be careful, conservative, and avoid unsupported specificity.\n"
            "3. Do not reject uncommon, advanced, or difficult topics. Instead, teach the same topic in the clearest grade-appropriate form possible.\n"
            "4. If revision feedback exists, treat it as a priority and correct those weaknesses first.\n"
            "5. Avoid repetitive phrasing, motivational filler, and generic textbook-style padding.\n"
            "6. Avoid markdown tables, HTML, bullet spam, and formatting that can break downstream parsing.\n"
            "7. Do not invent formulas, examples, or factual claims that are not reasonably supported by the evidence pack or the supplied concept framing.\n\n"
            "How to write the material:\n"
            "1. Build from intuitive entry point to formal understanding.\n"
            "2. Introduce the central idea clearly before adding complexity.\n"
            "3. Clarify what the concept is, why it matters, and how it is used or reasoned about.\n"
            "4. When the concept involves process, derivation, workflow, experiment, or procedure, explain it in ordered steps.\n"
            "5. When the concept is descriptive, theoretical, or interpretive, prefer clear paragraphs and precise bullets rather than forcing procedural steps.\n"
            "6. Use examples only when they genuinely improve understanding.\n"
            "7. Include formulas only when they are relevant, meaningful, and teachable for this concept.\n"
            "8. Make the quick revision section compact, high-yield, and genuinely useful for recall.\n\n"
            "Quality standards for full_study_material:\n"
            "- It should feel like polished lesson content, not rough notes.\n"
            "- It should be concept-specific, coherent, and logically sequenced.\n"
            "- It should reflect the likely misconceptions and learning order implied by the coverage map and teaching plan.\n"
            "- It should balance clarity with correctness.\n"
            "- It should not over-explain trivial points or skip essential bridges in reasoning.\n\n"
            "Quality standards for quick_revision:\n"
            "- Summarize only the most important points.\n"
            "- Focus on exam/revision usefulness, not full re-explanation.\n"
            "- Keep it concise, memorable, and structured for rapid recall.\n\n"
            "Quality standards for examples:\n"
            "- Include only concept-relevant examples.\n"
            "- Prefer examples that illuminate understanding, not decorative examples.\n"
            "- Do not produce empty, generic, or repetitive examples.\n\n"
            "Quality standards for formulas:\n"
            "- Include only formulas directly relevant to the concept.\n"
            "- Omit formulas if the concept does not genuinely require them.\n"
            "- Do not list symbolic expressions without educational value.\n\n"
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
            "Field guidance:\n"
            "- concept_level should be a compact label such as micro, mid, or macro.\n"
            "- complexity_score should be a numeric string from 0 to 1 reflecting instructional complexity.\n"
            "- required_depth should indicate how deeply the concept should be taught at this level.\n"
            "- word_count should reflect the approximate word count of full_study_material.\n"
            "- sections_complete should be true only if the content is genuinely complete for this concept.\n"
            "- grounded_to_sources should be true only if the content materially reflects the evidence pack.\n"
            "- refinement_used should be true only if revision feedback materially shaped the output.\n\n"
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
