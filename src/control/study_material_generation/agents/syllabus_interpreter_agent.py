from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class SyllabusInterpreterAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="SyllabusInterpreterAgent",
            goal="Transform a concept into clear, grade-level coverage objectives.",
            backstory="Curriculum expert who decomposes school concepts into teachable parts.",
        )

    def execute(
        self,
        *,
        subject_name: str,
        grade_level: str,
        concept_name: str,
        concept_description: str | None,
        learner_profile: str | None,
        evidence_pack: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence_text = self.format_evidence_pack(
            evidence_pack,
            max_sources=3,
            max_snippets=4,
            max_chars_per_snippet=220,
        )
        prompt = (
            "You are the syllabus interpretation stage in a production learning-content pipeline.\n"
            "Your job is to convert a concept into a tightly scoped, grade-appropriate coverage map that downstream agents can trust.\n\n"
            f"Subject: {subject_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Concept: {concept_name}\n"
            f"Concept Description: {concept_description or 'N/A'}\n"
            f"Learner Profile: {learner_profile or 'General classroom learner'}\n"
            f"Evidence Pack:\n{evidence_text}\n\n"
            "Interpretation rules:\n"
            "1. Stay strictly on this exact concept. Do not drift into the full chapter, neighboring topics, or broad subject summaries.\n"
            "2. Use the evidence pack as the primary grounding source. If evidence is partial, keep the scope conservative and avoid unsupported specificity.\n"
            "3. If the concept is advanced for the stated grade, do not reject it. Instead, define the simplest accurate and teachable version of the same concept for this grade.\n"
            "4. Prioritize conceptual clarity, teachability, and classroom usefulness over encyclopedic completeness.\n"
            "5. Write for downstream instructional design, not for the student directly. Each item should be specific enough to guide lesson generation.\n\n"
            "What to produce:\n"
            "- objectives: 4 to 6 precise learning outcomes for this concept only.\n"
            "- prerequisites: 3 to 5 concrete prior ideas or skills students need before learning this concept.\n"
            "- misconceptions: 4 to 6 realistic mistakes, confusions, or false beliefs students may have about this concept.\n\n"
            "Quality requirements:\n"
            "- Objectives must be observable and teachable, not vague goals like 'understand the topic'.\n"
            "- Prerequisites must be truly necessary foundations, not generic study habits or broad subject labels.\n"
            "- Misconceptions must reflect plausible learner confusion and must be distinct from one another.\n"
            "- Keep every bullet concise, concept-specific, and grade-appropriate.\n"
            "- Avoid repeating the concept name mechanically in every line.\n"
            "- Avoid filler, generic pedagogy advice, and meta commentary.\n\n"
            "Return strict JSON only with keys: objectives, prerequisites, misconceptions."
        )
        data = self.run_json_task(
            prompt,
            required_keys=["objectives", "prerequisites", "misconceptions"],
        )
        objectives = self.to_list(data.get("objectives"), [])
        prerequisites = self.to_list(data.get("prerequisites"), [])
        misconceptions = self.to_list(data.get("misconceptions"), [])
        if not objectives or not prerequisites or not misconceptions:
            raise ValueError("SyllabusInterpreterAgent produced incomplete concept mapping.")
        return {
            "objectives": objectives[:6],
            "prerequisites": prerequisites[:5],
            "misconceptions": misconceptions[:6],
        }
