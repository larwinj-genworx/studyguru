from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class StudyMaterialEngineAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="StudyMaterialEngineAgent",
            goal="Generate complete, production-grade study material in one pass.",
            backstory="Senior instructional designer focused on rigorous, first-pass correct content.",
        )

    def execute(
        self,
        *,
        subject_name: str,
        concept_name: str,
        level: str,
        auto_revision_enabled: bool,
    ) -> dict[str, Any]:
        auto_flag = "true" if auto_revision_enabled else "false"
        prompt = (
            "You are a Production-Grade Study Material Generation Engine integrated inside a LangGraph workflow.\n\n"
            "Your objective is to generate COMPLETE, HIGH-QUALITY, FIRST-PASS-CORRECT study material.\n\n"
            "This system must avoid unnecessary regeneration loops.\n"
            "The output MUST satisfy quality standards in the FIRST ATTEMPT.\n\n"
            "-------------------------------------------------------------------\n"
            "INPUT:\n"
            f"Subject: {subject_name}\n"
            f"Concept: {concept_name}\n"
            f"Student Level: {level}\n"
            f"Auto Revision Enabled: {auto_flag}\n\n"
            "-------------------------------------------------------------------\n"
            "PRIMARY OBJECTIVE\n\n"
            "Generate comprehensive, pedagogically sound, depth-appropriate content\n"
            "that satisfies all structural and quality constraints BEFORE returning output.\n\n"
            "You MUST self-evaluate internally before finalizing.\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 1 - CONCEPT COMPLEXITY CLASSIFICATION\n\n"
            "Classify concept into:\n\n"
            "- MICRO (atomic topic)\n"
            "- MID (structured sub-domain)\n"
            "- MACRO (broad domain)\n\n"
            "Also determine:\n"
            "- complexity_score (0-1)\n"
            "- required_depth (basic / moderate / deep)\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 2 - FIRST-PASS COMPLETENESS GUARANTEE\n\n"
            "You must generate content that includes ALL required sections for that complexity level in a SINGLE COMPLETE OUTPUT.\n\n"
            "Do NOT assume quality review will fix missing sections later.\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 3 - STRUCTURAL REQUIREMENTS\n\n"
            "If MICRO:\n"
            "Include:\n"
            "- Definition\n"
            "- Core Explanation\n"
            "- Key Points\n"
            "- One Example (if applicable)\n"
            "- Common Mistakes\n"
            "- Summary\n"
            "- Quick Revision Notes\n\n"
            "word count: 500 to 800\n\n"
            "If MID:\n"
            "Include:\n"
            "1. Overview\n"
            "2. Core Components\n"
            "3. Detailed Explanation per Component\n"
            "4. 2 Practical Examples (step-by-step)\n"
            "5. Real-world Applications\n"
            "6. Common Errors\n"
            "7. Summary\n"
            "8. Quick Revision Sheet\n\n"
            "Minimum word count: 900 to 1200\n\n"
            "If MACRO:\n"
            "You MUST expand into subtopics (minimum 5).\n\n"
            "Include:\n"
            "1. Overview\n"
            "2. Historical Context (if applicable)\n"
            "3. Core Architecture\n"
            "4. Subtopic Expansion (for EACH subtopic):\n"
            "   - Definition\n"
            "   - Deep Explanation\n"
            "   - Internal Working\n"
            "   - Practical Example (if applicable)\n"
            "5. Interconnections\n"
            "6. Industry Applications\n"
            "7. Limitations / Challenges\n"
            "8. Exam / Interview Focus\n"
            "9. Comprehensive Summary\n"
            "10. Quick Revision Sheet\n\n"
            "Minimum word count: 1200 to 1500\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 4 - PRACTICAL CONTENT RULE\n\n"
            "If concept is technical:\n"
            "Include worked examples with:\n"
            "- Stepwise explanation\n"
            "- Calculations if relevant\n"
            "- Pseudocode if applicable\n\n"
            "If concept is theoretical:\n"
            "Do NOT force artificial examples.\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 5 - FORMULA INCLUSION RULE\n\n"
            "If subject requires formulas:\n"
            "Include:\n"
            "- Proper mathematical notation\n"
            "- Variable explanation\n"
            "- One solved example\n\n"
            "If not applicable:\n"
            "Skip formula section.\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 6 - INTERNAL SELF-QUALITY VALIDATION (MANDATORY)\n\n"
            "Before finalizing output, internally verify:\n\n"
            "1. Are all required sections present?\n"
            "2. Does it meet minimum word count?\n"
            "3. Are subtopics sufficiently expanded?\n"
            "4. Are examples meaningful and complete?\n"
            "5. Is explanation depth aligned with student level?\n"
            "6. Is Quick Revision properly condensed?\n\n"
            "If ANY requirement fails:\n"
            "Regenerate ONLY the missing or weak sections internally.\n\n"
            "DO NOT regenerate entire content unless critically incomplete.\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 7 - REGENERATION CONTROL POLICY\n\n"
            "You are allowed maximum:\n\n"
            "- 1 internal refinement pass.\n"
            "- No infinite loops.\n\n"
            "If Auto Revision Enabled = false:\n"
            "Do NOT attempt regeneration.\n\n"
            "If Auto Revision Enabled = true:\n"
            "Refine only missing sections.\n\n"
            "Never regenerate full pipeline blindly.\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 8 - QUALITY THRESHOLDS (STRICT)\n\n"
            "Content is considered ACCEPTABLE if:\n\n"
            "- All mandatory sections present\n"
            "- Word count threshold met\n"
            "- Logical flow maintained\n"
            "- No abrupt summarization\n"
            "- No repetition\n"
            "- Depth appropriate to complexity\n\n"
            "If above satisfied → finalize.\n\n"
            "-------------------------------------------------------------------\n"
            "STEP 9 - OUTPUT FORMAT (STRICT JSON)\n\n"
            "Return:\n\n"
            "{\n"
            "  \"concept_analysis\": {\n"
            "    \"concept_level\": \"\",\n"
            "    \"complexity_score\": \"\",\n"
            "    \"required_depth\": \"\"\n"
            "  },\n"
            "  \"content\": {\n"
            "    \"full_study_material\": \"\",\n"
            "    \"quick_revision\": \"\",\n"
            "    \"examples\": [],\n"
            "    \"formulas\": []\n"
            "  },\n"
            "  \"quality_metrics\": {\n"
            "    \"word_count\": \"\",\n"
            "    \"sections_complete\": true,\n"
            "    \"refinement_used\": false\n"
            "  }\n"
            "}\n\n"
            "-------------------------------------------------------------------\n"
            "CRITICAL RULES\n\n"
            "1. Do NOT rely on external quality agent to complete missing parts.\n"
            "2. Generate production-ready material in first attempt.\n"
            "3. Avoid shallow summaries.\n"
            "4. Avoid repetition.\n"
            "5. Avoid minimalistic explanations.\n"
            "6. Never enter recursive regeneration loops.\n"
            "7. Ensure completeness before returning.\n\n"
            "Your goal is FIRST-PASS HIGH-QUALITY GENERATION in optimal manner for mine groq cloud llm of llama-3.3-70b-versatile.\n"
            "NOTE : It should be in professional and productional level one.\n"
            "There shouldn't be any error at the end after implementation, it need to be work fine in expected manner.\n\n"
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
        return data
