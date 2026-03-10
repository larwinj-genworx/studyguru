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
    prompt_text: str | None = None
    focus_area: str | None = None
    complexity_level: str | None = None
    visual_style: str | None = None
    generator_name: str | None = None
    explanation: str | None = None
    learning_points: list[str] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    pedagogical_score: float = 0.0
    created_at: datetime
    approved_at: datetime | None = None


class ConceptImageCollectionResponse(BaseModel):
    subject_id: str
    subject_name: str
    concept_id: str
    concept_name: str
    material_version: int
    prompt_text: str | None = None
    focus_area: str | None = None
    complexity_level: str | None = None
    images: list[ConceptImageAssetResponse] = Field(default_factory=list)


class ConceptImageGenerationRequest(BaseModel):
    prompt: str | None = Field(default=None, max_length=600)
    refresh: bool = False
