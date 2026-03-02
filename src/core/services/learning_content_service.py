from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

from src.schemas.study_material import (
    LearningContent,
    LearningSection,
    MaterialLifecycleStatus,
    ConceptContentPack,
)


CONTENT_SCHEMA_VERSION = "v1"


def build_learning_content(
    *,
    subject_name: str,
    grade_level: str,
    concept_id: str,
    concept_name: str,
    concept_pack: ConceptContentPack | None,
    engine_output: dict[str, Any] | None,
    formula_cards: list[dict[str, Any]] | None,
    generated_at: datetime,
    status: MaterialLifecycleStatus,
    version: int,
) -> LearningContent:
    core = concept_pack
    definition = (core.definition if core else "").strip()
    intuition = (core.intuition if core else "").strip()
    key_steps = list(core.key_steps) if core else []
    common_mistakes = list(core.common_mistakes) if core else []
    recap = list(core.recap) if core else []
    examples = list(core.examples) if core else []
    formulas = list(core.formulas) if core else []

    engine_content = (engine_output or {}).get("content") or {}
    full_text = str(engine_content.get("full_study_material", "")).strip()
    quick_revision_text = str(engine_content.get("quick_revision", "")).strip()
    concept_analysis = (engine_output or {}).get("concept_analysis") or {}

    highlights = _compact_list(recap[:5]) or _compact_list(key_steps[:5])

    metadata = {
        "subject": subject_name,
        "grade_level": grade_level,
        "concept_id": concept_id,
        "concept_name": concept_name,
        "generated_at": generated_at.isoformat(),
        "status": status.value,
        "version": version,
        "concept_level": concept_analysis.get("concept_level"),
        "complexity_score": concept_analysis.get("complexity_score"),
        "required_depth": concept_analysis.get("required_depth"),
    }

    sections: list[LearningSection] = []

    overview_blocks: list[dict[str, Any]] = []
    if definition:
        overview_blocks.append({"type": "paragraph", "text": definition})
    if intuition:
        overview_blocks.append({"type": "paragraph", "text": intuition})
    if highlights:
        overview_blocks.append(
            {
                "type": "callout",
                "variant": "highlight",
                "title": "Key Highlights",
                "content": highlights,
            }
        )
    sections.append(
        LearningSection(
            id=_slugify("Overview"),
            title="Overview",
            level=2,
            blocks=overview_blocks,
            children=[],
        )
    )

    core_children: list[LearningSection] = []
    for index, step in enumerate(key_steps, start=1):
        title = _short_title(step, fallback=f"Step {index}")
        core_children.append(
            LearningSection(
                id=_slugify(f"step-{index}-{title}"),
                title=f"Step {index}: {title}",
                level=3,
                blocks=[{"type": "paragraph", "text": step}],
                children=[],
            )
        )
    core_blocks: list[dict[str, Any]] = []
    if key_steps:
        core_blocks.append({"type": "list", "style": "number", "items": key_steps})
    if highlights:
        core_blocks.append(
            {
                "type": "callout",
                "variant": "takeaway",
                "title": "Why This Matters",
                "content": highlights,
            }
        )
    sections.append(
        LearningSection(
            id=_slugify("Core Concepts"),
            title="Core Concepts",
            level=2,
            blocks=core_blocks,
            children=core_children,
        )
    )

    explanation_blocks = _split_text_with_code(full_text)
    if explanation_blocks:
        sections.append(
            LearningSection(
                id=_slugify("Detailed Explanation"),
                title="Detailed Explanation",
                level=2,
                blocks=explanation_blocks,
                children=[],
            )
        )

    if examples:
        example_children: list[LearningSection] = []
        for index, example in enumerate(examples, start=1):
            steps = _split_example_steps(example)
            example_children.append(
                LearningSection(
                    id=_slugify(f"example-{index}"),
                    title=f"Example {index}",
                    level=3,
                    blocks=[
                        {
                            "type": "example",
                            "title": f"Example {index}",
                            "steps": steps,
                        }
                    ],
                    children=[],
                )
            )
        sections.append(
            LearningSection(
                id=_slugify("Practical Examples"),
                title="Practical Examples",
                level=2,
                blocks=[],
                children=example_children,
            )
        )

    formula_blocks = _build_formula_blocks(formula_cards, formulas)
    if formula_blocks:
        sections.append(
            LearningSection(
                id=_slugify("Formulas"),
                title="Formulas",
                level=2,
                blocks=formula_blocks,
                children=[],
            )
        )

    if highlights:
        sections.append(
            LearningSection(
                id=_slugify("Key Notes"),
                title="Key Notes",
                level=2,
                blocks=[
                    {
                        "type": "callout",
                        "variant": "note",
                        "title": "Key Notes",
                        "content": highlights,
                    }
                ],
                children=[],
            )
        )

    if common_mistakes:
        sections.append(
            LearningSection(
                id=_slugify("Common Mistakes"),
                title="Common Mistakes",
                level=2,
                blocks=[
                    {
                        "type": "callout",
                        "variant": "warning",
                        "title": "Watch Out For",
                        "content": common_mistakes,
                    }
                ],
                children=[],
            )
        )

    if recap:
        sections.append(
            LearningSection(
                id=_slugify("Summary"),
                title="Summary",
                level=2,
                blocks=[{"type": "list", "style": "bullet", "items": recap}],
                children=[],
            )
        )

    quick_revision_items = _split_bullets(quick_revision_text) or _compact_list(recap)
    if quick_revision_items:
        sections.append(
            LearningSection(
                id=_slugify("Quick Revision"),
                title="Quick Revision",
                level=2,
                blocks=[{"type": "list", "style": "bullet", "items": quick_revision_items}],
                children=[],
            )
        )

    return LearningContent(
        metadata=metadata,
        highlights=highlights,
        sections=sections,
    )


def build_search_text(content: LearningContent) -> str:
    pieces: list[str] = []
    metadata = content.metadata or {}
    pieces.extend([str(metadata.get("subject", "")), str(metadata.get("concept_name", ""))])
    pieces.extend(content.highlights or [])

    def _collect(section: LearningSection) -> None:
        pieces.append(section.title)
        for block in section.blocks:
            pieces.extend(_block_text(block))
        for child in section.children:
            _collect(child)

    for section in content.sections:
        _collect(section)

    cleaned = [piece.strip() for piece in pieces if piece and str(piece).strip()]
    return " ".join(cleaned).strip()


def _block_text(block: dict[str, Any]) -> Iterable[str]:
    block_type = block.get("type")
    if block_type == "paragraph":
        return [str(block.get("text", ""))]
    if block_type == "list":
        return [*map(str, block.get("items") or [])]
    if block_type == "formula":
        items = [str(block.get("formula", ""))]
        variables = block.get("variables") or []
        for item in variables:
            if isinstance(item, dict):
                items.append(f"{item.get('symbol', '')} {item.get('meaning', '')}".strip())
        extra = block.get("explanation") or ""
        if extra:
            items.append(str(extra))
        return items
    if block_type == "code":
        return [str(block.get("code", ""))]
    if block_type == "callout":
        content = block.get("content") or []
        if isinstance(content, list):
            return [*map(str, content)]
        return [str(content)]
    if block_type == "example":
        items = [str(block.get("title", ""))]
        items.extend([*map(str, block.get("steps") or [])])
        result = block.get("result")
        if result:
            items.append(str(result))
        return items
    return []


def _split_paragraphs(text: str) -> list[str]:
    if not text:
        return []
    chunks = re.split(r"\n\s*\n", text.strip())
    paragraphs = []
    for chunk in chunks:
        cleaned = " ".join(chunk.strip().split())
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def _split_text_with_code(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    blocks: list[dict[str, Any]] = []
    if "```" not in text:
        return [{"type": "paragraph", "text": paragraph} for paragraph in _split_paragraphs(text)]

    parts = text.split("```")
    for index, part in enumerate(parts):
        if index % 2 == 1:
            lines = [line.rstrip() for line in part.strip().splitlines()]
            if not lines:
                continue
            language = "text"
            if lines and re.fullmatch(r"[A-Za-z]+", lines[0].strip()):
                language = lines[0].strip().lower()
                code = "\n".join(lines[1:]).strip()
            else:
                code = "\n".join(lines).strip()
            if code:
                blocks.append({"type": "code", "language": language, "code": code})
        else:
            for paragraph in _split_paragraphs(part):
                blocks.append({"type": "paragraph", "text": paragraph})
    return blocks


def _split_bullets(text: str) -> list[str]:
    if not text:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned: list[str] = []
    for line in lines:
        item = re.sub(r"^[\-\*\u2022\d\.\)]\s+", "", line).strip()
        if item:
            cleaned.append(item)
    if cleaned:
        return cleaned
    sentences = [sentence.strip() for sentence in re.split(r"\.\s+", text) if sentence.strip()]
    return sentences[:8]


def _split_example_steps(example_text: str) -> list[str]:
    if not example_text:
        return []
    lines = [line.strip() for line in example_text.splitlines() if line.strip()]
    if len(lines) > 1:
        return lines[:6]
    sentences = [sentence.strip() for sentence in re.split(r"\.\s+", example_text) if sentence.strip()]
    if len(sentences) > 1:
        return sentences[:6]
    return [example_text.strip()]


def _build_formula_blocks(
    formula_cards: list[dict[str, Any]] | None,
    fallback_formulas: list[str],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    cards = formula_cards or []
    if not cards and fallback_formulas:
        for formula in fallback_formulas:
            variables = [{"symbol": symbol, "meaning": "Variable in the formula"} for symbol in _extract_variables(formula)]
            blocks.append(
                {
                    "type": "formula",
                    "formula": formula,
                    "variables": variables,
                    "explanation": "",
                }
            )
        return blocks

    for card in cards:
        if not isinstance(card, dict):
            continue
        formula = str(card.get("formula", "")).strip()
        if not formula:
            continue
        variables = card.get("variables") or []
        blocks.append(
            {
                "type": "formula",
                "formula": formula,
                "variables": variables,
                "explanation": str(card.get("explanation", "")).strip(),
                "example": str(card.get("example", "")).strip(),
            }
        )
    return blocks


def _extract_variables(formula: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*", formula)
    ignore = {"sin", "cos", "tan", "log", "ln", "sqrt"}
    cleaned = []
    for token in tokens:
        if token.lower() in ignore:
            continue
        if token not in cleaned:
            cleaned.append(token)
    return cleaned[:8]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "section"


def _short_title(text: str, fallback: str) -> str:
    if not text:
        return fallback
    words = text.split()
    trimmed = " ".join(words[:5]).strip()
    return trimmed if trimmed else fallback


def _compact_list(values: list[str]) -> list[str]:
    return [str(item).strip() for item in values if str(item).strip()][:8]
