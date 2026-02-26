from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ReviewStatus(str, Enum):
    pending_review = "pending_review"
    approved = "approved"


class MaterialLifecycleStatus(str, Enum):
    unavailable = "unavailable"
    draft = "draft"
    approved = "approved"
    published = "published"


class ConceptCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=600)


class ConceptBulkCreate(BaseModel):
    concepts: list[ConceptCreate] = Field(min_length=1, max_length=50)


class SubjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    grade_level: str = Field(min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=600)


class AdminMaterialJobCreate(BaseModel):
    subject_id: str
    concept_ids: list[str] = Field(min_length=1, max_length=30)
    learner_profile: str | None = Field(default=None, max_length=500)


class AdminMaterialRegenerateRequest(BaseModel):
    learner_profile: str | None = Field(default=None, max_length=500)
    revision_note: str | None = Field(default=None, max_length=500)


class AdminMaterialApproveRequest(BaseModel):
    concept_ids: list[str] | None = Field(default=None, max_length=30)
    approval_note: str | None = Field(default=None, max_length=500)


class StudentConceptSelection(BaseModel):
    concept_ids: list[str] = Field(min_length=1, max_length=30)


class ArtifactIndex(BaseModel):
    pptx: str | None = None
    docx: str | None = None
    pdf: str | None = None
    quiz_json: str | None = None
    flashcards_json: str | None = None
    resources_json: str | None = None
    zip: str | None = None
    extras: dict[str, str] = Field(default_factory=dict)


class ConceptMaterialResponse(BaseModel):
    concept_id: str
    concept_name: str
    lifecycle_status: MaterialLifecycleStatus
    version: int
    source_job_id: str
    artifact_index: ArtifactIndex
    generated_at: datetime
    approved_at: datetime | None = None
    published_at: datetime | None = None


class ConceptResponse(BaseModel):
    concept_id: str
    name: str
    description: str | None = None
    created_at: datetime
    material_status: MaterialLifecycleStatus = MaterialLifecycleStatus.unavailable
    material_version: int = 0


class SubjectResponse(BaseModel):
    subject_id: str
    name: str
    grade_level: str
    description: str | None = None
    published: bool
    created_at: datetime
    updated_at: datetime
    concepts: list[ConceptResponse] = Field(default_factory=list)


class MaterialJobStatusResponse(BaseModel):
    job_id: str
    subject_id: str
    concept_ids: list[str]
    status: JobStatus
    review_status: ReviewStatus
    progress: int = Field(ge=0, le=100)
    concept_statuses: dict[str, str] = Field(default_factory=dict)
    artifact_index: ArtifactIndex = Field(default_factory=ArtifactIndex)
    concept_artifacts: dict[str, ArtifactIndex] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    reviewer_note: str | None = None
    created_at: datetime
    updated_at: datetime


class ConceptContentPack(BaseModel):
    concept_id: str
    concept_name: str
    definition: str
    intuition: str
    key_steps: list[str]
    common_mistakes: list[str]
    examples: list[str]
    mcqs: list[dict[str, Any]]
    flashcards: list[dict[str, str]]
    references: list[dict[str, str]]
    recap: list[str]


class ConceptMaterialRecord(BaseModel):
    concept_id: str
    concept_name: str
    lifecycle_status: MaterialLifecycleStatus = MaterialLifecycleStatus.draft
    version: int = 1
    source_job_id: str
    artifact_index: ArtifactIndex = Field(default_factory=ArtifactIndex)
    generated_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    published_at: datetime | None = None


class SubjectRecord(BaseModel):
    subject_id: str
    name: str
    grade_level: str
    description: str | None = None
    published: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    concept_meta: dict[str, ConceptResponse] = Field(default_factory=dict)
    materials: dict[str, ConceptMaterialRecord] = Field(default_factory=dict)


class JobRecord(BaseModel):
    job_id: str = Field(default_factory=lambda: uuid4().hex)
    subject_id: str
    concept_ids: list[str]
    learner_profile: str | None = None
    revision_note: str | None = None
    status: JobStatus = JobStatus.queued
    review_status: ReviewStatus = ReviewStatus.pending_review
    progress: int = 0
    concept_statuses: dict[str, str] = Field(default_factory=dict)
    artifact_index: ArtifactIndex = Field(default_factory=ArtifactIndex)
    concept_artifacts: dict[str, ArtifactIndex] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    reviewer_note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None
    output_dir: str | None = None

    def touch(self) -> None:
        self.updated_at = utc_now()
