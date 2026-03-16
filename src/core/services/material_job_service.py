from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status

from src.core.services.study_material_service import artifact_index_from_json
from src.data.models.postgres.models import Concept, ConceptMaterial, MaterialJob, MaterialJobConcept
from src.schemas.study_material import (
    AdminMaterialJobCreate,
    ArtifactIndex,
    JobRecord,
    JobStatus,
    MaterialJobStatusResponse,
    MaterialLifecycleStatus,
    ReviewStatus,
)


_ALLOWED_ARTIFACTS = {
    "pdf",
    "quick_revision_pdf",
    "quiz_json",
    "flashcards_json",
    "resources_json",
    "study_material_json",
    "zip",
}


def validate_job_request(payload: AdminMaterialJobCreate, concepts: list[Concept]) -> list[str]:
    if not concepts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No concepts are available under this subject.",
        )
    concept_ids = list(dict.fromkeys(payload.concept_ids))
    concept_id_set = {concept.id for concept in concepts}
    missing = [concept_id for concept_id in concept_ids if concept_id not in concept_id_set]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown concept IDs: {missing}",
        )
    return concept_ids


def build_job(payload: AdminMaterialJobCreate, subject_id: str, revision_note: str | None = None) -> MaterialJob:
    return MaterialJob(
        subject_id=subject_id,
        learner_profile=payload.learner_profile,
        revision_note=revision_note,
        status=JobStatus.queued,
        review_status=ReviewStatus.pending_review,
        progress=0,
        artifact_index={},
        errors=[],
        output_dir=None,
    )


def build_job_concept(job_id: str, concept_id: str) -> MaterialJobConcept:
    return MaterialJobConcept(
        job_id=job_id,
        concept_id=concept_id,
        status="queued",
        artifact_index={},
    )


def to_job_record(job: MaterialJob, job_concepts: list[MaterialJobConcept]) -> JobRecord:
    concept_ids = [row.concept_id for row in job_concepts]
    concept_statuses = {row.concept_id: row.status for row in job_concepts}
    concept_artifacts = {
        row.concept_id: artifact_index_from_json(row.artifact_index)
        for row in job_concepts
    }
    return JobRecord(
        job_id=job.id,
        subject_id=job.subject_id,
        concept_ids=concept_ids,
        learner_profile=job.learner_profile,
        revision_note=job.revision_note,
        status=job.status,
        review_status=job.review_status,
        progress=job.progress,
        concept_statuses=concept_statuses,
        artifact_index=artifact_index_from_json(job.artifact_index),
        concept_artifacts=concept_artifacts,
        errors=list(job.errors or []),
        reviewer_note=job.reviewer_note,
        created_at=job.created_at,
        updated_at=job.updated_at,
        reviewed_at=job.reviewed_at,
        output_dir=job.output_dir,
    )


def to_job_response(job_record: JobRecord) -> MaterialJobStatusResponse:
    return MaterialJobStatusResponse(
        job_id=job_record.job_id,
        subject_id=job_record.subject_id,
        concept_ids=job_record.concept_ids,
        status=job_record.status,
        review_status=job_record.review_status,
        progress=job_record.progress,
        concept_statuses=job_record.concept_statuses,
        artifact_index=job_record.artifact_index,
        concept_artifacts=job_record.concept_artifacts,
        errors=job_record.errors,
        reviewer_note=job_record.reviewer_note,
        created_at=job_record.created_at,
        updated_at=job_record.updated_at,
    )


def ensure_job_approvable(job: MaterialJob) -> None:
    if job.status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not completed yet.",
        )
    if job.review_status == ReviewStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This job is already approved.",
        )


def build_concept_material(
    subject_id: str,
    concept_id: str,
    source_job_id: str,
    artifact_index: dict,
    version: int,
    approved_at: datetime | None = None,
) -> ConceptMaterial:
    return ConceptMaterial(
        subject_id=subject_id,
        concept_id=concept_id,
        lifecycle_status=MaterialLifecycleStatus.approved,
        version=version,
        source_job_id=source_job_id,
        artifact_index=artifact_index,
        approved_at=approved_at,
    )


def validate_artifact_name(artifact_name: str) -> None:
    if artifact_name not in _ALLOWED_ARTIFACTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported artifact name: {artifact_name}",
        )


def assert_completed(job: JobRecord) -> None:
    if job.status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Artifacts are available only after job completion.",
        )


def _job_relative_root(job: JobRecord) -> str:
    if not job.output_dir:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact directory not found.")
    return job.output_dir


def resolve_job_artifact_relative_path(job: JobRecord, artifact_name: str) -> str:
    validate_artifact_name(artifact_name)
    assert_completed(job)
    path_value = getattr(job.artifact_index, artifact_name, None)
    if not path_value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return f"{_job_relative_root(job)}/{path_value}"


def resolve_concept_artifact_relative_path(job: JobRecord, concept_id: str, artifact_name: str) -> str:
    validate_artifact_name(artifact_name)
    assert_completed(job)
    concept_artifact = job.concept_artifacts.get(concept_id)
    if not concept_artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generated artifact found for concept '{concept_id}'.",
        )
    path_value = getattr(concept_artifact, artifact_name, None)
    if not path_value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return f"{_job_relative_root(job)}/concepts/{concept_id}/{path_value}"


def resolve_published_concept_artifact_relative_path(job: JobRecord, concept_id: str, artifact_name: str) -> str:
    validate_artifact_name(artifact_name)
    path_value = getattr(job.concept_artifacts.get(concept_id) or ArtifactIndex(), artifact_name, None)
    if not path_value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published artifact not found.")
    return f"{_job_relative_root(job)}/concepts/{concept_id}/{path_value}"


def resolve_published_subject_artifact_relative_path(job: JobRecord, artifact_name: str) -> str:
    validate_artifact_name(artifact_name)
    path_value = getattr(job.artifact_index, artifact_name, None)
    if not path_value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.")
    return f"{_job_relative_root(job)}/{path_value}"
