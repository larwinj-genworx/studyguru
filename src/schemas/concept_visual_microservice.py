from __future__ import annotations

from pydantic import BaseModel, Field

from src.schemas.study_material import LearningContent


class ConceptVisualRenderRequest(BaseModel):
    subject_id: str
    subject_name: str
    grade_level: str
    concept_id: str
    concept_name: str
    concept_description: str | None = None
    concept_material_id: str
    prompt: str | None = Field(default=None, max_length=600)
    max_variants: int = Field(default=3, ge=1, le=4)
    content: LearningContent


class ConceptVisualRenderAsset(BaseModel):
    title: str
    caption: str | None = None
    alt_text: str | None = None
    focus_area: str
    complexity_level: str
    visual_style: str
    generator_name: str
    explanation: str | None = None
    learning_points: list[str] = Field(default_factory=list)
    pedagogical_score: float = Field(default=0.0, ge=0, le=1)
    relative_image_path: str
    relative_thumbnail_path: str
    mime_type: str = "image/png"
    width: int
    height: int
    file_size_bytes: int
    render_spec: dict = Field(default_factory=dict)
    fingerprint: str | None = None


class ConceptVisualRenderResponse(BaseModel):
    prompt: str | None = None
    focus_area: str
    complexity_level: str
    assets: list[ConceptVisualRenderAsset] = Field(default_factory=list)
