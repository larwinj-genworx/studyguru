from __future__ import annotations

import ast
import json
import re
from datetime import datetime
from typing import Any, Iterable

from src.schemas.study_material import (
    LearningContent,
    LearningSection,
    MaterialLifecycleStatus,
    ConceptContentPack,
)


CONTENT_SCHEMA_VERSION = "v2"


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
    stepwise_breakdown_required = bool(getattr(core, "stepwise_breakdown_required", False)) if core else False
    key_steps = _normalize_key_steps(list(core.key_steps) if core else [])
    common_mistakes = list(core.common_mistakes) if core else []
    recap = list(core.recap) if core else []
    examples = list(core.examples) if core else []
    formulas = list(core.formulas) if core else []
    references = list(core.references) if core else []

    engine_content = (engine_output or {}).get("content") or {}
    full_text = str(engine_content.get("full_study_material", "")).strip()
    quick_revision_text = str(engine_content.get("quick_revision", "")).strip()
    concept_analysis = (engine_output or {}).get("concept_analysis") or {}
    grounding = (engine_output or {}).get("grounding") or {}

    highlights = _compact_list(recap[:5]) or _compact_list(key_steps[:5])
    should_render_step_section = stepwise_breakdown_required and len(key_steps) >= 2

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
        "retrieval_status": grounding.get("retrieval_status"),
        "source_count": grounding.get("source_count", len(references)),
        "retrieved_at": grounding.get("retrieved_at"),
        "stepwise_breakdown_required": stepwise_breakdown_required,
        "queries": grounding.get("queries", []),
        "sources": grounding.get("sources") or [
            {
                "title": str(item.get("title", "Resource")).strip(),
                "url": str(item.get("url", "")).strip(),
                "domain": str(item.get("note", "")).strip(),
            }
            for item in references
            if isinstance(item, dict)
        ],
    }

    sections: list[LearningSection] = []

    overview_blocks: list[dict[str, Any]] = []
    if definition:
        overview_blocks.append({"type": "paragraph", "text": definition})
    if intuition:
        overview_blocks.append({"type": "paragraph", "text": intuition})
    sections.append(
        LearningSection(
            id=_slugify("Overview"),
            title="Overview",
            level=2,
            blocks=overview_blocks,
            children=[],
        )
    )

    if highlights:
        sections.append(
            LearningSection(
                id=_slugify("Key Highlights"),
                title="Key Highlights",
                level=2,
                blocks=[{"type": "list", "style": "bullet", "items": highlights}],
                children=[],
            )
        )

    if should_render_step_section:
        sections.append(
            LearningSection(
                id=_slugify("Key Steps"),
                title="Key Steps",
                level=2,
                blocks=[{"type": "list", "style": "number", "items": key_steps}],
                children=[],
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

    practical_required = True
    if core is not None:
        practical_required = bool(getattr(core, "practical_examples_required", True))
    if examples and practical_required:
        example_children: list[LearningSection] = []
        for index, example in enumerate(examples, start=1):
            parsed = _parse_example_payload(str(example))
            steps = parsed["steps"]
            title = parsed["title"] or f"Example {index}"
            prompt = parsed["prompt"]
            result = parsed["result"]
            example_children.append(
                LearningSection(
                    id=_slugify(f"example-{index}"),
                    title=f"Example {index}",
                    level=3,
                    blocks=[
                        {
                            "type": "example",
                            "title": title,
                            "prompt": prompt,
                            "steps": steps,
                            "result": result,
                            "example_style": parsed["example_style"],
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

    if references:
        source_items: list[str] = []
        for item in references:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "Resource")).strip() or "Resource"
            url = str(item.get("url", "")).strip()
            note = str(item.get("note", "")).strip()
            text = f"{title} - {url}" if url else title
            if note:
                text = f"{text} ({note})"
            source_items.append(text)
        if source_items:
            sections.append(
                LearningSection(
                    id=_slugify("Sources and Further Reading"),
                    title="Sources & Further Reading",
                    level=2,
                    blocks=[
                        {
                            "type": "callout",
                            "variant": "note",
                            "title": "How This Material Was Grounded",
                            "content": [
                                f"Retrieval status: {metadata.get('retrieval_status') or 'unknown'}",
                                f"Source count: {metadata.get('source_count') or len(source_items)}",
                            ],
                        },
                        {"type": "list", "style": "bullet", "items": source_items[:8]},
                    ],
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


def _normalize_key_steps(items: list[str]) -> list[str]:
    cleaned_steps: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = str(item).strip()
        if not cleaned:
            continue
        normalized = re.sub(r"\s+", " ", cleaned.lower()).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned_steps.append(cleaned)
    return cleaned_steps


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
        prompt = block.get("prompt")
        if prompt:
            items.append(str(prompt))
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


def _split_long_paragraph(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", cleaned) if sentence.strip()]
    if len(sentences) <= 2 and len(cleaned) <= 260:
        return [cleaned]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
            continue
        if len(current) + len(sentence) + 1 <= 260:
            current = f"{current} {sentence}"
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def _split_text_blocks(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    lines = text.splitlines()
    blocks: list[dict[str, Any]] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []
    list_style: str | None = None

    def _flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = " ".join(line.strip() for line in paragraph_lines if line.strip()).strip()
        paragraph_lines.clear()
        for chunk in _split_long_paragraph(paragraph):
            blocks.append({"type": "paragraph", "text": chunk})

    def _flush_list() -> None:
        nonlocal list_style
        if list_items:
            blocks.append({"type": "list", "style": list_style or "bullet", "items": list_items.copy()})
            list_items.clear()
        list_style = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            _flush_paragraph()
            _flush_list()
            continue
        number_match = re.match(r"^(\d+)[\.\)]\s+(.*)$", stripped)
        if number_match:
            _flush_paragraph()
            if list_style not in (None, "number"):
                _flush_list()
            list_style = "number"
            item = number_match.group(2).strip()
            if item:
                list_items.append(item)
            continue
        bullet_match = re.match(r"^[\-\*\u2022]\s+(.*)$", stripped)
        if bullet_match:
            _flush_paragraph()
            if list_style not in (None, "bullet"):
                _flush_list()
            list_style = "bullet"
            item = bullet_match.group(1).strip()
            if item:
                list_items.append(item)
            continue
        if list_items:
            _flush_list()
        paragraph_lines.append(stripped)

    _flush_paragraph()
    _flush_list()
    return blocks


def _split_text_with_code(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    blocks: list[dict[str, Any]] = []
    if "```" not in text:
        return _split_text_blocks(text)

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
            blocks.extend(_split_text_blocks(part))
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
        return lines
    sentences = [sentence.strip() for sentence in re.split(r"\.\s+", example_text) if sentence.strip()]
    if len(sentences) > 1:
        return sentences
    cleaned = example_text.strip()
    return [cleaned] if cleaned else []


def _build_formula_blocks(
    formula_cards: list[dict[str, Any]] | None,
    fallback_formulas: list[str],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    cards = formula_cards or []
    if not cards and fallback_formulas:
        for index, formula in enumerate(fallback_formulas, start=1):
            parsed = _parse_formula_payload(str(formula))
            formula_text = parsed["formula"]
            variables = parsed["variables"] or [
                {"symbol": symbol, "meaning": "Variable in the formula"} for symbol in _extract_variables(formula_text)
            ]
            blocks.append(
                {
                    "type": "formula",
                    "title": _formula_title(formula_text, variables, index),
                    "formula": formula_text,
                    "variables": variables,
                    "explanation": parsed["explanation"],
                }
            )
        return blocks

    for index, card in enumerate(cards, start=1):
        if not isinstance(card, dict):
            continue
        raw_formula = str(card.get("formula", "")).strip()
        parsed = _parse_formula_payload(raw_formula)
        formula = parsed["formula"]
        if not formula:
            continue
        variables = _normalize_variables(card.get("variables")) or parsed["variables"]
        explanation = str(card.get("explanation", "")).strip() or parsed["explanation"]
        blocks.append(
            {
                "type": "formula",
                "title": _formula_title(formula, variables, index),
                "formula": formula,
                "variables": variables,
                "explanation": explanation,
                "example": str(card.get("example", "")).strip(),
            }
        )
    return blocks


def normalize_learning_content(content: LearningContent) -> LearningContent:
    def _normalize_section(section: LearningSection) -> None:
        for block in section.blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "example":
                steps = block.get("steps") or []
                if (
                    isinstance(steps, list)
                    and len(steps) == 1
                    and isinstance(steps[0], str)
                    and steps[0].strip().startswith(("{", "["))
                ):
                    parsed = _parse_example_payload(steps[0])
                    if parsed["title"]:
                        block["title"] = parsed["title"]
                    if parsed["prompt"]:
                        block["prompt"] = parsed["prompt"]
                    if parsed["steps"]:
                        block["steps"] = parsed["steps"]
                    if parsed["result"]:
                        block["result"] = parsed["result"]
                    if parsed["example_style"]:
                        block["example_style"] = parsed["example_style"]
            if block.get("type") == "formula":
                if not block.get("title"):
                    formula_text = str(block.get("formula", "")).strip()
                    variables = _normalize_variables(block.get("variables"))
                    block["title"] = _formula_title(formula_text, variables, 1)
        for child in section.children:
            _normalize_section(child)

    def _normalize_section_list(sections: list[LearningSection]) -> list[LearningSection]:
        normalized_sections: list[LearningSection] = []
        for section in sections:
            _normalize_section(section)
            section.children = _normalize_section_list(section.children or [])
            normalized = _cleanup_learning_section(section)
            if normalized is None:
                continue
            normalized_sections.append(normalized)
        return normalized_sections

    content.sections = _normalize_section_list(content.sections or [])
    return content


def _cleanup_learning_section(section: LearningSection) -> LearningSection | None:
    normalized_title = section.title.strip().lower()
    if normalized_title not in {"key steps", "core ideas"}:
        return section if section.blocks or section.children else None

    cleaned_blocks: list[dict[str, Any]] = []
    numbered_step_items: list[str] = []
    for block in section.blocks:
        if not isinstance(block, dict):
            continue
        if (
            block.get("type") == "callout"
            and str(block.get("title", "")).strip().lower() == "why this matters"
        ):
            continue
        if block.get("type") == "list" and str(block.get("style", "")).strip().lower() == "number":
            step_items = _normalize_key_steps([str(item).strip() for item in block.get("items", []) if str(item).strip()])
            if step_items:
                block["items"] = step_items
                numbered_step_items = step_items
            else:
                continue
        cleaned_blocks.append(block)

    section.blocks = cleaned_blocks
    if numbered_step_items and _children_duplicate_step_items(section.children, numbered_step_items):
        section.children = []

    if len(numbered_step_items) < 2 and not _has_meaningful_non_step_blocks(section.blocks):
        return None

    if numbered_step_items:
        section.title = "Key Steps"
    elif normalized_title == "core ideas":
        section.title = "Key Highlights"

    return section if section.blocks or section.children else None


def _children_duplicate_step_items(children: list[LearningSection], step_items: list[str]) -> bool:
    if not children or not step_items:
        return False
    child_step_texts = [_extract_step_child_text(child) for child in children]
    if not child_step_texts or any(not text for text in child_step_texts):
        return False
    normalized_items = {normalize_text(item) for item in step_items if normalize_text(item)}
    normalized_children = {normalize_text(text) for text in child_step_texts if normalize_text(text)}
    return bool(normalized_items) and normalized_children.issubset(normalized_items)


def _extract_step_child_text(section: LearningSection) -> str:
    for block in section.blocks:
        if isinstance(block, dict) and block.get("type") == "paragraph":
            text = str(block.get("text", "")).strip()
            if text:
                return text
    return section.title


def _has_meaningful_non_step_blocks(blocks: list[dict[str, Any]]) -> bool:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type", "")).strip().lower()
        if block_type != "list":
            return True
        if str(block.get("style", "")).strip().lower() != "number":
            items = [str(item).strip() for item in block.get("items", []) if str(item).strip()]
            if items:
                return True
    return False


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


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


def _parse_example_payload(example_text: str) -> dict[str, Any]:
    parsed = _parse_structured_text(example_text)
    if isinstance(parsed, dict):
        title = str(
            parsed.get("example")
            or parsed.get("title")
            or ""
        ).strip()
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
            parsed.get("stepwise_solution")
            or parsed.get("steps")
            or parsed.get("solution")
            or parsed.get("working")
            or parsed.get("process")
        )
        explanation = parsed.get("explanation") or parsed.get("note")
        if isinstance(raw_steps, list):
            steps = [str(item).strip() for item in raw_steps if str(item).strip()]
        elif isinstance(raw_steps, str):
            steps = _split_example_steps(raw_steps)
        else:
            steps = []
        if not steps and explanation:
            steps = _split_example_steps(str(explanation))
        result = str(parsed.get("final_answer") or parsed.get("answer") or parsed.get("result") or "").strip()
        if not steps:
            steps = _split_example_steps(example_text)
        if prompt and title and prompt.lower() == title.lower():
            title = ""
        deduped: list[str] = []
        seen: set[str] = set()
        for step in steps:
            cleaned = str(step).strip()
            if not cleaned:
                continue
            normalized = re.sub(r"\s+", " ", cleaned.lower()).strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(cleaned)
        steps = deduped
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
    steps = _split_example_steps(example_text)
    return {"title": "", "prompt": "", "steps": steps, "result": "", "example_style": ""}


def _parse_formula_payload(formula_text: str) -> dict[str, Any]:
    parsed = _parse_structured_text(formula_text)
    if isinstance(parsed, dict):
        formula = str(
            parsed.get("formula") or parsed.get("expression") or parsed.get("eqn") or formula_text
        ).strip()
        variables = _normalize_variables(parsed.get("variables"))
        explanation = str(parsed.get("explanation") or parsed.get("note") or "").strip()
        return {"formula": formula, "variables": variables, "explanation": explanation}
    return {"formula": formula_text.strip(), "variables": [], "explanation": ""}


def _normalize_variables(raw_variables: Any) -> list[dict[str, str]]:
    if isinstance(raw_variables, dict):
        cleaned = []
        for symbol, meaning in raw_variables.items():
            symbol_text = str(symbol).strip()
            meaning_text = str(meaning).strip()
            if symbol_text and meaning_text:
                cleaned.append({"symbol": symbol_text, "meaning": meaning_text})
        return cleaned
    if isinstance(raw_variables, list):
        cleaned = []
        for item in raw_variables:
            if not isinstance(item, dict):
                continue
            symbol_text = str(item.get("symbol", "")).strip()
            meaning_text = str(item.get("meaning", "")).strip()
            if symbol_text and meaning_text:
                cleaned.append({"symbol": symbol_text, "meaning": meaning_text})
        return cleaned
    return []


def _formula_title(formula: str, variables: list[dict[str, str]], index: int) -> str:
    if not formula:
        return f"Formula {index}"
    for delimiter in ("=", "≈", "≃", "≅", "→"):
        if delimiter in formula:
            left = formula.split(delimiter, 1)[0].strip()
            if 1 <= len(left) <= 12:
                for variable in variables:
                    if variable.get("symbol") == left and variable.get("meaning"):
                        return f"{variable['meaning']} Formula"
                return f"Formula for {left}"
            break
    return f"Formula {index}"


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
