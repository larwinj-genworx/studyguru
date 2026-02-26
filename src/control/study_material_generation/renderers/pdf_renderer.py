from __future__ import annotations

from pathlib import Path

from ..models import ConceptContentPack


class PdfRenderer:
    def render(
        self,
        output_dir: Path,
        subject_name: str,
        grade_level: str,
        concept_packs: list[ConceptContentPack],
    ) -> Path:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        output_path = output_dir / "quick_revision.pdf"
        pdf = canvas.Canvas(str(output_path), pagesize=A4)
        width, height = A4
        margin = 50

        y = height - margin
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(margin, y, f"{subject_name} - Quick Revision")
        y -= 20
        pdf.setFont("Helvetica", 11)
        pdf.drawString(margin, y, f"Level: {grade_level}")
        y -= 24

        for pack in concept_packs:
            y = self._ensure_space(pdf, y, height, margin)
            pdf.setFont("Helvetica-Bold", 13)
            pdf.drawString(margin, y, pack.concept_name)
            y -= 16

            lines = [
                f"Definition: {pack.definition}",
                f"Intuition: {pack.intuition}",
                "Key Steps:",
                *[f"- {step}" for step in pack.key_steps[:5]],
                "Common Mistakes:",
                *[f"- {mistake}" for mistake in pack.common_mistakes[:4]],
                "Recap:",
                *[f"- {item}" for item in pack.recap[:4]],
            ]

            pdf.setFont("Helvetica", 10)
            for line in lines:
                y = self._ensure_space(pdf, y, height, margin)
                pdf.drawString(margin, y, line[:130])
                y -= 12
            y -= 8

        pdf.save()
        return output_path

    @staticmethod
    def _ensure_space(pdf: canvas.Canvas, y: float, height: float, margin: float) -> float:
        if y < margin + 30:
            pdf.showPage()
            return height - margin
        return y
