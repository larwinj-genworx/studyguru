from __future__ import annotations

from typing import Any

from .base import BaseStructuredAgent
from src.config.settings import Settings


class StudentPedagogyAgent(BaseStructuredAgent):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            role="StudentPedagogyAgent",
            goal="Create an engaging, low-friction teaching plan for the concept.",
            backstory="Pedagogy planner focused on easy understanding and student attention.",
        )

    def execute(
        self,
        *,
        concept_name: str,
        grade_level: str,
        coverage_map: dict[str, Any],
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
            "You are the pedagogy planning stage in a production learning-content pipeline.\n"
            "Your job is to turn the coverage map into a teaching sequence that reduces confusion, builds confidence gradually, and prepares downstream agents to generate high-quality lesson content.\n\n"
            f"Concept: {concept_name}\n"
            f"Grade Level: {grade_level}\n"
            f"Coverage Map: {coverage_map}\n"
            f"Learner Profile: {learner_profile or 'General classroom learner'}\n"
            f"Evidence Pack:\n{evidence_text}\n\n"
            "Planning rules:\n"
            "1. Stay strictly within this concept and the provided coverage map.\n"
            "2. Use the evidence pack to decide which idea should be introduced first, what should be simplified, what examples are more intuitive, and which misconceptions need early correction.\n"
            "3. Sequence learning from easiest mental entry point to deeper understanding.\n"
            "4. If the concept is abstract or advanced for the grade, design a gentler conceptual ramp rather than skipping the concept.\n"
            "5. Prioritize clarity, low cognitive load, and teachability over cleverness or academic breadth.\n\n"
            "What to produce:\n"
            "- lesson_flow: 5 to 7 short, ordered steps describing how the lesson should progress.\n"
            "- teaching_tips: 4 to 6 highly practical teaching guidelines tailored to this concept, this grade, and the likely learner friction.\n\n"
            "Quality requirements for lesson_flow:\n"
            "- Each step must represent a real teaching move, not a vague statement.\n"
            "- The sequence should start with prior knowledge activation or intuitive anchoring when appropriate.\n"
            "- The middle steps should introduce the core idea, clarify confusion points, and deepen understanding gradually.\n"
            "- The final steps should reinforce, check understanding, or prepare for guided practice.\n"
            "- Do not repeat the same action in different wording.\n\n"
            "Quality requirements for teaching_tips:\n"
            "- Tips must be specific to this concept, not generic advice that fits any lesson.\n"
            "- Include guidance for pacing, misconception handling, representation choice, or example selection when relevant.\n"
            "- If the learner profile suggests low confidence, weak foundations, or attention challenges, reflect that in the tips.\n"
            "- Keep every tip concise and directly actionable.\n\n"
            "Avoid:\n"
            "- generic filler such as 'make it engaging' without saying how\n"
            "- broad chapter-level teaching advice\n"
            "- repeating objective text from the coverage map without pedagogical interpretation\n"
            "- meta commentary or markdown\n\n"
            "Return strict JSON only with keys: lesson_flow, teaching_tips."
        )
        data = self.run_json_task(
            prompt,
            required_keys=["lesson_flow", "teaching_tips"],
        )
        lesson_flow = self.to_list(data.get("lesson_flow"), [])
        teaching_tips = self.to_list(data.get("teaching_tips"), [])
        if not lesson_flow or not teaching_tips:
            raise ValueError("StudentPedagogyAgent produced incomplete pedagogical flow.")
        return {
            "lesson_flow": lesson_flow[:7],
            "teaching_tips": teaching_tips[:6],
        }
