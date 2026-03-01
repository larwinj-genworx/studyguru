from __future__ import annotations

from fastapi import HTTPException, status

from src.core.services import material_job_service, study_material_service
from src.data.repositories import material_job_repository, study_material_repository
from src.schemas.study_material import JobRecord, SubjectRecord


async def get_job(job_id: str) -> JobRecord:
    job = await material_job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
    job_concepts = await material_job_repository.get_job_concepts(job_id)
    return material_job_service.to_job_record(job, job_concepts)


async def update_job(job_record: JobRecord) -> None:
    job_record.touch()
    job = await material_job_repository.get_job(job_record.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
    job.status = job_record.status
    job.review_status = job_record.review_status
    job.progress = job_record.progress
    job.artifact_index = study_material_service.artifact_index_to_json(job_record.artifact_index)
    job.errors = list(job_record.errors)
    job.reviewer_note = job_record.reviewer_note
    job.updated_at = job_record.updated_at
    job.reviewed_at = job_record.reviewed_at
    job.output_dir = job_record.output_dir
    job.revision_note = job_record.revision_note
    job.learner_profile = job_record.learner_profile
    await material_job_repository.update_job(job)

    concept_updates: dict[str, dict] = {}
    for concept_id in job_record.concept_ids:
        values: dict = {}
        if concept_id in job_record.concept_statuses:
            values["status"] = job_record.concept_statuses[concept_id]
        if concept_id in job_record.concept_artifacts:
            values["artifact_index"] = study_material_service.artifact_index_to_json(
                job_record.concept_artifacts[concept_id]
            )
        if values:
            concept_updates[concept_id] = values
    if concept_updates:
        await material_job_repository.update_job_concepts(job_record.job_id, concept_updates)


async def update_job_fields(job_record: JobRecord) -> None:
    job_record.touch()
    job = await material_job_repository.get_job(job_record.job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material job not found.")
    job.status = job_record.status
    job.review_status = job_record.review_status
    job.progress = job_record.progress
    job.artifact_index = study_material_service.artifact_index_to_json(job_record.artifact_index)
    job.errors = list(job_record.errors)
    job.reviewer_note = job_record.reviewer_note
    job.updated_at = job_record.updated_at
    job.reviewed_at = job_record.reviewed_at
    job.output_dir = job_record.output_dir
    job.revision_note = job_record.revision_note
    job.learner_profile = job_record.learner_profile
    await material_job_repository.update_job(job)


async def set_concept_status(job_id: str, concept_id: str, status_text: str) -> None:
    await material_job_repository.set_concept_status(job_id, concept_id, status_text)


async def get_subject_record(subject_id: str) -> SubjectRecord:
    subject = await study_material_repository.get_subject(subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concepts = await study_material_repository.list_concepts(subject_id)
    latest_materials = await study_material_repository.get_latest_materials(
        [concept.id for concept in concepts]
    )
    return study_material_service.to_subject_record(subject, concepts, latest_materials)
