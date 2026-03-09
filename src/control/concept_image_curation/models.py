from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class VisualQueryPlan:
    label: str
    search_hint: str
    caption_hint: str


@dataclass(slots=True)
class PageImageCandidate:
    title: str
    caption: str
    alt_text: str
    intent_label: str
    source_page_url: str
    source_image_url: str
    source_domain: str
    relevance_score: float
    width_hint: int | None = None
    height_hint: int | None = None
    mime_type_hint: str | None = None
