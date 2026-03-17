from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape

from src.schemas.study_material import ConceptContentPack


class PdfRenderer:
    def render(
        self,
        output_dir: Path,
        subject_name: str,
        grade_level: str,
        concept_packs: list[ConceptContentPack],
    ) -> Path:
        return self._build_document(
            output_dir=output_dir,
            subject_name=subject_name,
            grade_level=grade_level,
            concept_packs=concept_packs,
            filename="study_material.pdf",
            variant="full",
        )

    def render_quick_revision(
        self,
        output_dir: Path,
        subject_name: str,
        grade_level: str,
        concept_packs: list[ConceptContentPack],
    ) -> Path:
        return self._build_document(
            output_dir=output_dir,
            subject_name=subject_name,
            grade_level=grade_level,
            concept_packs=concept_packs,
            filename="quick_revision.pdf",
            variant="quick",
        )

    def _build_document(
        self,
        *,
        output_dir: Path,
        subject_name: str,
        grade_level: str,
        concept_packs: list[ConceptContentPack],
        filename: str,
        variant: str,
    ) -> Path:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            KeepTogether,
            ListFlowable,
            ListItem,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )

        output_path = output_dir / filename
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=2.1 * cm,
            rightMargin=2.1 * cm,
            topMargin=2.0 * cm,
            bottomMargin=2.0 * cm,
            title=f"{subject_name} Study Material",
            author="StudyGuru",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#475569"),
            spaceAfter=2,
        )
        concept_style = ParagraphStyle(
            "ConceptHeading",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=10,
            spaceAfter=6,
        )
        section_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#1f2937"),
            spaceBefore=8,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=4,
        )
        body_small = ParagraphStyle(
            "BodySmall",
            parent=body_style,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#374151"),
        )

        def clean_text(value: str | None) -> str:
            if not value:
                return ""
            return escape(str(value).strip()).replace("\n", "<br/>")

        def list_flow(items: list[str], bullet_type: str = "bullet", item_style: ParagraphStyle = body_style):
            cleaned = [clean_text(item) for item in items if str(item).strip()]
            if not cleaned:
                return None
            list_items = [ListItem(Paragraph(text, item_style)) for text in cleaned]
            return ListFlowable(
                list_items,
                bulletType=bullet_type,
                leftIndent=18,
                bulletFontName="Helvetica",
                bulletFontSize=item_style.fontSize,
                bulletColor=colors.HexColor("#1f2937"),
                spaceAfter=6,
            )

        def parse_structured_text(raw_text: str):
            text = str(raw_text or "").strip()
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

        def split_example_steps(example_text: str) -> list[str]:
            text = str(example_text or "").strip()
            if not text:
                return []
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if len(lines) > 1:
                return lines
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", text)
                if sentence.strip()
            ]
            if len(sentences) > 1:
                return sentences
            return [text]

        def parse_example_payload(example_text: str) -> dict[str, str | list[str]]:
            parsed = parse_structured_text(example_text)
            if isinstance(parsed, dict):
                title = str(parsed.get("title") or parsed.get("example") or "").strip()
                prompt = str(
                    parsed.get("prompt")
                    or parsed.get("question")
                    or parsed.get("problem")
                    or parsed.get("task")
                    or parsed.get("description")
                    or parsed.get("context")
                    or ""
                ).strip()
                raw_steps = (
                    parsed.get("steps")
                    or parsed.get("stepwise_solution")
                    or parsed.get("solution")
                    or parsed.get("working")
                    or parsed.get("process")
                )
                if isinstance(raw_steps, list):
                    steps = [str(item).strip() for item in raw_steps if str(item).strip()]
                elif isinstance(raw_steps, str):
                    steps = split_example_steps(raw_steps)
                else:
                    steps = []
                if not steps:
                    explanation = parsed.get("explanation") or parsed.get("note")
                    if explanation:
                        steps = split_example_steps(str(explanation))
                result = str(parsed.get("result") or parsed.get("answer") or parsed.get("final_answer") or "").strip()
                example_style = str(parsed.get("example_type") or parsed.get("style") or parsed.get("type") or "").strip()
                return {
                    "title": title,
                    "prompt": prompt,
                    "steps": steps,
                    "result": result,
                    "example_style": example_style,
                }
            if isinstance(parsed, list):
                steps = [str(item).strip() for item in parsed if str(item).strip()]
                return {"title": "", "prompt": "", "steps": steps, "result": "", "example_style": ""}
            return {
                "title": "",
                "prompt": "",
                "steps": split_example_steps(example_text),
                "result": "",
                "example_style": "",
            }

        def format_example_label(example_style: str) -> str:
            normalized = str(example_style or "").strip().lower()
            if normalized == "derivation":
                return "Derivation"
            if normalized == "calculation":
                return "Worked Calculation"
            if normalized == "scenario":
                return "Application"
            if not normalized:
                return ""
            return " ".join(part.capitalize() for part in re.split(r"[\s_-]+", normalized) if part)

        def example_flow(example_text: str, index: int) -> list:
            parsed = parse_example_payload(example_text)
            title = str(parsed.get("title") or "").strip()
            prompt = str(parsed.get("prompt") or "").strip()
            result = str(parsed.get("result") or "").strip()
            example_style = format_example_label(str(parsed.get("example_style") or ""))
            steps = [str(item).strip() for item in parsed.get("steps", []) if str(item).strip()]
            heading = title or f"Worked Example {index}"
            if example_style:
                heading = f"{heading} ({example_style})"

            flowables = [Paragraph(f"<b>Example {index}.</b> {clean_text(heading)}", body_style)]
            if prompt:
                flowables.append(Paragraph(f"<b>Problem.</b> {clean_text(prompt)}", body_small))
            if steps:
                step_list = list_flow(steps, bullet_type="1", item_style=body_small)
                if step_list:
                    flowables.append(step_list)
            if result:
                flowables.append(Paragraph(f"<b>Result.</b> {clean_text(result)}", body_small))
            flowables.append(Spacer(1, 4))
            return [KeepTogether(flowables)]

        def header_footer(canvas, doc_ref):
            canvas.saveState()
            canvas.setFont("Helvetica", 9)
            canvas.setFillColor(colors.HexColor("#64748b"))
            canvas.drawString(doc_ref.leftMargin, doc_ref.pagesize[1] - doc_ref.topMargin + 6, subject_name)
            canvas.drawRightString(
                doc_ref.pagesize[0] - doc_ref.rightMargin,
                doc_ref.bottomMargin - 12,
                f"Page {doc_ref.page}",
            )
            canvas.restoreState()

        story = []
        title_suffix = "Study Material" if variant == "full" else "Quick Revision"
        story.append(Paragraph(f"{subject_name} {title_suffix}", title_style))
        story.append(Paragraph(f"Grade Level: {grade_level}", subtitle_style))
        story.append(Paragraph(datetime.utcnow().strftime("Generated on %B %d, %Y"), subtitle_style))
        story.append(Spacer(1, 12))

        if concept_packs:
            story.append(Paragraph("Concepts Covered", section_style))
            names_list = list_flow([pack.concept_name for pack in concept_packs])
            if names_list:
                story.append(names_list)
            story.append(Spacer(1, 6))
        else:
            story.append(Paragraph("No concept content is available yet.", body_style))
            doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
            return output_path

        for idx, pack in enumerate(concept_packs):
            if idx > 0:
                story.append(PageBreak())

            story.append(Paragraph(pack.concept_name, concept_style))
            if pack.definition:
                story.append(Paragraph(f"<b>Definition.</b> {clean_text(pack.definition)}", body_style))
            if pack.intuition and variant == "full":
                story.append(Paragraph(f"<b>Intuition.</b> {clean_text(pack.intuition)}", body_style))

            if pack.formulas:
                story.append(Paragraph("Key Formulas", section_style))
                formulas_list = list_flow(pack.formulas, bullet_type="bullet", item_style=body_small)
                if formulas_list:
                    story.append(formulas_list)

            if pack.stepwise_breakdown_required and pack.key_steps:
                story.append(Paragraph("Key Steps", section_style))
                steps_list = list_flow(pack.key_steps, item_style=body_style)
                if steps_list:
                    story.append(steps_list)

            if variant == "full" and pack.examples:
                story.append(Paragraph("Practical Examples", section_style))
                for example_index, example in enumerate(pack.examples, start=1):
                    story.extend(example_flow(example, example_index))

            if pack.common_mistakes:
                story.append(Paragraph("Common Mistakes", section_style))
                mistakes_list = list_flow(pack.common_mistakes, item_style=body_style)
                if mistakes_list:
                    story.append(mistakes_list)

            if pack.recap:
                story.append(Paragraph("Quick Recap", section_style))
                recap_list = list_flow(pack.recap, item_style=body_style)
                if recap_list:
                    story.append(recap_list)

            if variant == "full" and pack.references:
                story.append(Paragraph("Learning Resources", section_style))
                resources = []
                for ref in pack.references:
                    title = str(ref.get("title") or "Resource").strip()
                    url = str(ref.get("url") or "").strip()
                    if url:
                        resources.append(f"{title} — {url}")
                    else:
                        resources.append(title)
                resources_list = list_flow(resources, item_style=body_small)
                if resources_list:
                    story.append(resources_list)

        doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
        return output_path
