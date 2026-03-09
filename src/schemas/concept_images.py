from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ConceptImageStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ConceptImageAssetResponse(BaseModel):
    image_id: str
    status: ConceptImageStatus
    title: str
    caption: str | None = None
    alt_text: str | None = None
    intent_label: str | None = None
    source_page_url: str | None = None
    source_image_url: str | None = None
    source_domain: str | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    relevance_score: float = 0.0
    created_at: datetime
    approved_at: datetime | None = None


class ConceptImageCollectionResponse(BaseModel):
    subject_id: str
    subject_name: str
    concept_id: str
    concept_name: str
    material_version: int
    images: list[ConceptImageAssetResponse] = Field(default_factory=list)
