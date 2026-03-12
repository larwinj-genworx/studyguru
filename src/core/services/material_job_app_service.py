from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from src.config.settings import get_settings
from src.control.study_material_generation.agents import build_agent_registry
from src.control.study_material_generation.graph.workflow import MaterialWorkflow
from src.control.study_material_generation.renderers.json_renderer import JsonRenderer
from src.control.study_material_generation.renderers.pdf_renderer import PdfRenderer
from src.control.study_material_generation.renderers.study_material_json_renderer import StudyMaterialJsonRenderer
from src.core.services import material_job_service
from src.core.services.object_storage_service import get_object_storage_service
from src.core.services.study_material_app_service import _safe_remove_job_outputs
from src.data.repositories import material_job_repository, study_material_repository
from src.schemas.study_material import (
    AdminMaterialApproveRequest,
    AdminMaterialJobCreate,
    AdminMaterialRegenerateRequest,
    JobStatus,
    MaterialJobStatusResponse,
    MaterialLifecycleStatus,
    ReviewStatus,
)

logger = logging.getLogger("uvicorn.error")

_settings = get_settings()
_storage = get_object_storage_service()
_workflow: MaterialWorkflow | None = None


def _ensure_workflow() -> MaterialWorkflow:
    global _workflow
    if _workflow is not None:
        return _workflow
    _workflow = MaterialWorkflow(
        settings=_settings,
        agents=build_agent_registry(_settings),
        pdf_renderer=PdfRenderer(),
        json_renderer=JsonRenderer(),
        study_material_json_renderer=StudyMaterialJsonRenderer(),
    )
    return _workflow


async def _get_subject_for_owner(subject_id: str, owner_id: str):
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    return subject


async def _assert_job_owner(job_id: str, owner_id: str):
    job = await material_job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
    await _get_subject_for_owner(job.subject_id, owner_id)
    return job


async def create_admin_job(payload: AdminMaterialJobCreate, owner_id: str) -> MaterialJobStatusResponse:
    subject = await _get_subject_for_owner(payload.subject_id, owner_id)
    concepts = await study_material_repository.list_concepts(subject.id)
    concept_ids = material_job_service.validate_job_request(payload, concepts)
    job_model = material_job_service.build_job(payload, subject.id)
    job_model = await material_job_repository.create_job(job_model, concept_ids)
    job_concepts = await material_job_repository.get_job_concepts(job_model.id)
    job_record = material_job_service.to_job_record(job_model, job_concepts)
    asyncio.create_task(_run_job(job_record.job_id))
    return material_job_service.to_job_response(job_record)


async def regenerate_job(
    source_job_id: str,
    payload: AdminMaterialRegenerateRequest,
    owner_id: str,
) -> MaterialJobStatusResponse:
    source_job = await _assert_job_owner(source_job_id, owner_id)
    job_concepts = await material_job_repository.get_job_concepts(source_job.id)
    source_record = material_job_service.to_job_record(source_job, job_concepts)
    create_payload = AdminMaterialJobCreate(
        subject_id=source_record.subject_id,
        concept_ids=source_record.concept_ids,
        learner_profile=payload.learner_profile or source_record.learner_profile,
    )
    revision_note = payload.revision_note or source_record.reviewer_note
    subject = await _get_subject_for_owner(create_payload.subject_id, owner_id)
    concepts = await study_material_repository.list_concepts(subject.id)
    concept_ids = material_job_service.validate_job_request(create_payload, concepts)
    job_model = material_job_service.build_job(create_payload, subject.id, revision_note=revision_note)
    job_model = await material_job_repository.create_job(job_model, concept_ids)
    job_concepts = await material_job_repository.get_job_concepts(job_model.id)
    job_record = material_job_service.to_job_record(job_model, job_concepts)
    asyncio.create_task(_run_job(job_record.job_id))
    return material_job_service.to_job_response(job_record)


async def get_job_status(job_id: str, owner_id: str) -> MaterialJobStatusResponse:
    job = await _assert_job_owner(job_id, owner_id)
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    return material_job_service.to_job_response(material_job_service.to_job_record(job, job_concepts))


async def list_admin_jobs(subject_id: str | None = None, owner_id: str | None = None) -> list[MaterialJobStatusResponse]:
    jobs = await material_job_repository.list_jobs(subject_id, owner_id=owner_id)
    responses: list[MaterialJobStatusResponse] = []
    for job in jobs:
        job_concepts = await material_job_repository.get_job_concepts(job.id)
        responses.append(
            material_job_service.to_job_response(
                material_job_service.to_job_record(job, job_concepts)
            )
        )
    return responses


async def approve_job(
    job_id: str,
    payload: AdminMaterialApproveRequest,
    owner_id: str,
) -> MaterialJobStatusResponse:
    job = await _assert_job_owner(job_id, owner_id)
    if job.status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not completed yet.",
        )
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    if job.review_status == ReviewStatus.approved:
        job_concept_ids = [row.concept_id for row in job_concepts]
        latest_materials = await study_material_repository.get_latest_materials(job_concept_ids)
        pending = [
            concept_id
            for concept_id in job_concept_ids
            if concept_id not in latest_materials
            or latest_materials[concept_id].source_job_id != job.id
        ]
        if not pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This job is already approved.",
            )
    job_concept_map = {row.concept_id: row for row in job_concepts}

    target_ids = payload.concept_ids or [row.concept_id for row in job_concepts]
    unknown = [concept_id for concept_id in target_ids if concept_id not in job_concept_map]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Concept artifacts missing in job output: {unknown}",
        )

    materials_to_update: list = []
    materials_to_create: list = []
    updated_concepts: list = []
    now = datetime.now(timezone.utc)
    existing_materials = await study_material_repository.get_materials_for_job(job.id, target_ids)
    for concept_id in target_ids:
        concept = await material_job_repository.get_concept(concept_id)
        if not concept:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown concept ID: {concept_id}",
            )
        job_concept = job_concept_map[concept_id]
        existing = existing_materials.get(concept_id)
        if existing:
            existing.lifecycle_status = MaterialLifecycleStatus.approved
            existing.approved_at = now
            if job_concept.artifact_index:
                existing.artifact_index = job_concept.artifact_index
            materials_to_update.append(existing)
            concept.material_status = MaterialLifecycleStatus.approved
            concept.material_version = existing.version
        else:
            latest_material = await study_material_repository.get_latest_material(concept_id)
            next_version = (latest_material.version + 1) if latest_material else 1
            materials_to_create.append(
                material_job_service.build_concept_material(
                    subject_id=job.subject_id,
                    concept_id=concept_id,
                    source_job_id=job.id,
                    artifact_index=job_concept.artifact_index or {},
                    version=next_version,
                    approved_at=now,
                )
            )
            concept.material_status = MaterialLifecycleStatus.approved
            concept.material_version = next_version
        updated_concepts.append(concept)

    if payload.approval_note is not None:
        job.reviewer_note = payload.approval_note
    job.updated_at = now

    if materials_to_create:
        await study_material_repository.create_concept_materials(materials_to_create)
    if materials_to_update:
        await study_material_repository.update_materials(materials_to_update)
    await study_material_repository.update_concepts(updated_concepts)
    job_concept_ids = [row.concept_id for row in job_concepts]
    latest_materials = await study_material_repository.get_latest_materials(job_concept_ids)
    all_approved = all(
        (
            latest_materials.get(concept_id)
            and latest_materials[concept_id].lifecycle_status
            in (MaterialLifecycleStatus.approved, MaterialLifecycleStatus.published)
            and latest_materials[concept_id].source_job_id == job.id
        )
        for concept_id in job_concept_ids
    )
    if all_approved:
        job.review_status = ReviewStatus.approved
        job.reviewed_at = now
    else:
        job.review_status = ReviewStatus.pending_review
    await material_job_repository.update_job(job)

    job_concepts = await material_job_repository.get_job_concepts(job.id)
    return material_job_service.to_job_response(material_job_service.to_job_record(job, job_concepts))


async def discard_job_concept(
    job_id: str,
    concept_id: str,
    owner_id: str,
) -> MaterialJobStatusResponse:
    job = await _assert_job_owner(job_id, owner_id)
    if job.status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not completed yet.",
        )
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    if not any(row.concept_id == concept_id for row in job_concepts):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concept artifact not found in this job.",
        )
    latest_material = await study_material_repository.get_latest_material(concept_id)
    if (
        latest_material
        and latest_material.source_job_id == job.id
        and latest_material.lifecycle_status
        in (MaterialLifecycleStatus.approved, MaterialLifecycleStatus.published)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete artifacts already approved from this job.",
        )
    await material_job_repository.delete_job_concepts(job.id, [concept_id])
    await study_material_repository.delete_materials_for_job(job.id, [concept_id])
    if job.output_dir:
        settings = get_settings()
        _safe_remove_job_outputs(
            settings.material_output_dir / job.output_dir / "concepts",
            [concept_id],
        )
        _storage.delete_prefix(
            _storage.material_area,
            f"{job.output_dir}/concepts/{concept_id}",
        )
    concept = await material_job_repository.get_concept(concept_id)
    if concept:
        latest_after_delete = await study_material_repository.get_latest_material(concept_id)
        if latest_after_delete:
            concept.material_status = latest_after_delete.lifecycle_status
            concept.material_version = latest_after_delete.version
        else:
            concept.material_status = MaterialLifecycleStatus.unavailable
            concept.material_version = 0
        await study_material_repository.update_concepts([concept])
    job.updated_at = datetime.now(timezone.utc)
    await material_job_repository.update_job(job)
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    return material_job_service.to_job_response(material_job_service.to_job_record(job, job_concepts))


async def get_job_artifact_path(job_id: str, artifact_name: str, owner_id: str):
    job = await _assert_job_owner(job_id, owner_id)
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    record = material_job_service.to_job_record(job, job_concepts)
    return material_job_service.resolve_job_artifact_relative_path(record, artifact_name)


async def get_job_concept_artifact_path(job_id: str, concept_id: str, artifact_name: str, owner_id: str):
    job = await _assert_job_owner(job_id, owner_id)
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    record = material_job_service.to_job_record(job, job_concepts)
    return material_job_service.resolve_concept_artifact_relative_path(record, concept_id, artifact_name)


async def get_published_concept_artifact_path(subject_id: str, concept_id: str, artifact_name: str):
    subject = await study_material_repository.get_subject(subject_id)
    if not subject or not subject.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject is not published.")
    material = await study_material_repository.get_latest_material(concept_id, published_only=True)
    if not material or material.lifecycle_status != MaterialLifecycleStatus.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published concept material not found.")
    job = await material_job_repository.get_job(material.source_job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    record = material_job_service.to_job_record(job, job_concepts)
    return material_job_service.resolve_published_concept_artifact_relative_path(
        record,
        concept_id,
        artifact_name,
    )


async def get_published_subject_artifact_path(subject_id: str, artifact_name: str):
    subject = await study_material_repository.get_subject(subject_id)
    if not subject or not subject.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject is not published.")
    concepts = await study_material_repository.list_concepts(subject_id)
    latest_materials = await study_material_repository.get_latest_materials(
        [concept.id for concept in concepts]
    )
    published_materials = [
        material
        for material in latest_materials.values()
        if material.lifecycle_status == MaterialLifecycleStatus.published
    ]
    if not published_materials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published materials not found for subject.",
        )
    latest = max(
        published_materials,
        key=lambda material: material.published_at or material.generated_at,
    )
    job = await material_job_repository.get_job(latest.source_job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
    job_concepts = await material_job_repository.get_job_concepts(job.id)
    record = material_job_service.to_job_record(job, job_concepts)
    return material_job_service.resolve_published_subject_artifact_relative_path(record, artifact_name)


async def _run_job(job_id: str) -> None:
    try:
        workflow = _ensure_workflow()
        await workflow.run(job_id)
    except Exception as exc:
        logger.exception("[MaterialJob:%s] Workflow execution failed.", job_id)
        job = await material_job_repository.get_job(job_id)
        if not job:
            return
        now = datetime.now(timezone.utc)
        job.status = JobStatus.failed
        job.errors = list(job.errors or []) + [str(exc)]
        job.progress = min(job.progress, 99)
        job.updated_at = now
        await material_job_repository.update_job(job)
