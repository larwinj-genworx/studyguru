from __future__ import annotations

from datetime import datetime, timezone
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile
import logging
import shutil
from pathlib import Path

from fastapi import HTTPException, status

from src.config.settings import get_settings
from src.core.services import enrollment_app_service, study_material_service, learning_content_service
from src.core.services.object_storage_service import get_object_storage_service
from src.data.repositories import study_material_repository, material_job_repository
from src.schemas.study_material import (
    AdminConceptPlanUpdateRequest,
    ConceptBulkCreate,
    ConceptMaterialResponse,
    ConceptResponse,
    ConceptBookmarkResponse,
    LearningContentResponse,
    LearningContentUpdate,
    MaterialLifecycleStatus,
    JobStatus,
    SubjectCreate,
    SubjectRecord,
    SubjectResponse,
)

_logger = logging.getLogger("uvicorn.error")
_storage = get_object_storage_service()


_BUNDLE_ARTIFACT_FIELDS = (
    "pdf",
    "quick_revision_pdf",
    "quiz_json",
    "flashcards_json",
    "resources_json",
    "study_material_json",
)


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
    return cleaned or "concept"


def _validate_topic_orders(
    topic_orders: list[int],
    *,
    existing_orders: set[int] | None = None,
) -> None:
    seen: set[int] = set(existing_orders or set())
    duplicates: list[int] = []
    for item in topic_orders:
        if item in seen:
            duplicates.append(item)
            continue
        seen.add(item)
    if duplicates:
        duplicate_text = ", ".join(str(item) for item in sorted(set(duplicates)))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Topic order values must be unique within a syllabus. Duplicates: {duplicate_text}",
        )


def _normalize_description(value: str | None) -> str:
    return (value or "").strip()


def _validate_published_subject_topic_plan(
    *,
    existing_concepts: list,
    submitted_items: list,
) -> None:
    existing_ids = [concept.id for concept in existing_concepts]
    submitted_existing_ids = [item.concept_id for item in submitted_items if item.concept_id]

    if submitted_existing_ids != existing_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Published topics stay locked in their current order. "
                "Add new topics after the existing syllabus sequence."
            ),
        )

    if any(item.concept_id for item in submitted_items[len(existing_concepts):]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Existing published topics cannot be moved after new draft topics.",
        )

    concept_map = {concept.id: concept for concept in existing_concepts}
    for item in submitted_items[: len(existing_concepts)]:
        concept = concept_map[item.concept_id]
        if (
            concept.name.strip() != item.name.strip()
            or _normalize_description(concept.description) != _normalize_description(item.description)
            or int(concept.pass_percentage) != int(item.pass_percentage)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Published topics cannot be edited here. "
                    "You can append new topics without changing the live sequence."
                ),
            )


async def create_subject(
    payload: SubjectCreate,
    owner_id: str,
    organization_id: str,
) -> SubjectResponse:
    subject = study_material_service.build_subject(payload, owner_id, organization_id)
    subject = await study_material_repository.create_subject(subject)
    await enrollment_app_service.sync_organization_subject_access(
        organization_id,
        subject_ids=[subject.id],
    )
    concepts: list = []
    return study_material_service.to_subject_response(subject, concepts)


async def add_concepts_bulk(
    subject_id: str,
    payload: ConceptBulkCreate,
    owner_id: str,
) -> SubjectResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    existing_concepts = await study_material_repository.list_concepts(subject_id)
    _validate_topic_orders(
        [concept.topic_order for concept in payload.concepts],
        existing_orders={concept.topic_order for concept in existing_concepts},
    )
    concepts = [
        study_material_service.build_concept(concept, subject_id)
        for concept in payload.concepts
    ]
    subject.updated_at = datetime.now(timezone.utc)
    await study_material_repository.add_concepts(concepts)
    await study_material_repository.update_subject(subject)
    concept_rows = await study_material_repository.list_concepts(subject_id)
    return study_material_service.to_subject_response(subject, concept_rows)


async def save_concept_plan(
    subject_id: str,
    payload: AdminConceptPlanUpdateRequest,
    owner_id: str,
) -> SubjectResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")

    existing_concepts = await study_material_repository.list_concepts(subject_id)
    if subject.published:
        _validate_published_subject_topic_plan(
            existing_concepts=existing_concepts,
            submitted_items=payload.concepts,
        )
    existing_map = {concept.id: concept for concept in existing_concepts}
    submitted_existing_ids = [
        item.concept_id
        for item in payload.concepts
        if item.concept_id
    ]
    if len(submitted_existing_ids) != len(set(submitted_existing_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each existing topic can only appear once in the topic plan.",
        )

    invalid_ids = sorted({concept_id for concept_id in submitted_existing_ids if concept_id not in existing_map})
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid concept IDs: {invalid_ids}",
        )

    submitted_existing_id_set = set(submitted_existing_ids)
    missing_existing_ids = [
        concept.id for concept in existing_concepts if concept.id not in submitted_existing_id_set
    ]
    if missing_existing_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All existing topics must remain in the topic planner when saving changes.",
        )

    updated_concepts: list = []
    new_concepts: list = []
    existing_count = len(existing_concepts)
    for topic_order, item in enumerate(payload.concepts, start=1):
        name = item.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each topic needs a name before saving the topic plan.",
            )
        description = item.description.strip() if item.description else None
        if item.concept_id:
            concept = existing_map[item.concept_id]
            concept.name = name
            concept.description = description
            concept.pass_percentage = item.pass_percentage
            concept.topic_order = topic_order
            updated_concepts.append(concept)
            continue

        if subject.published:
            topic_order = existing_count + len(new_concepts) + 1
        new_concepts.append(
            study_material_service.build_concept_from_plan_item(
                item,
                subject_id=subject_id,
                topic_order=topic_order,
            )
        )
        new_concepts[-1].description = description

    subject.updated_at = datetime.now(timezone.utc)
    await study_material_repository.save_concept_plan(
        updated_concepts=updated_concepts,
        new_concepts=new_concepts,
    )
    await study_material_repository.update_subject(subject)
    concept_rows = await study_material_repository.list_concepts(subject_id)
    return study_material_service.to_subject_response(subject, concept_rows)


async def get_subject(subject_id: str, owner_id: str) -> SubjectResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concepts = await study_material_repository.list_concepts(subject_id)
    return study_material_service.to_subject_response(subject, concepts)


async def list_admin_subjects(owner_id: str) -> list[SubjectResponse]:
    subjects = await study_material_repository.list_subjects_for_owner(owner_id)
    responses: list[SubjectResponse] = []
    for subject in subjects:
        concepts = await study_material_repository.list_concepts(subject.id)
        responses.append(study_material_service.to_subject_response(subject, concepts))
    return responses


async def list_published_subjects() -> list[SubjectResponse]:
    subjects = await study_material_repository.list_subjects(published_only=True)
    responses: list[SubjectResponse] = []
    for subject in subjects:
        concepts = await study_material_repository.list_concepts(subject.id)
        responses.append(study_material_service.to_subject_response(subject, concepts))
    return responses


async def list_subject_concepts(subject_id: str, published_only: bool = False) -> list[ConceptResponse]:
    subject = await study_material_repository.get_subject(subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    if published_only and not subject.published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not available for students.",
        )
    concepts = await study_material_repository.list_concepts(subject_id)
    if published_only:
        concepts = [
            concept
            for concept in concepts
            if concept.material_status == MaterialLifecycleStatus.published
        ]
    return [study_material_service.to_concept_response(concept) for concept in concepts]


async def list_subject_materials(
    subject_id: str,
    published_only: bool = False,
    owner_id: str | None = None,
) -> list[ConceptMaterialResponse]:
    subject = (
        await study_material_repository.get_subject_for_owner(subject_id, owner_id)
        if owner_id
        else await study_material_repository.get_subject(subject_id)
    )
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    if published_only and not subject.published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject is not published.",
        )
    concepts = await study_material_repository.list_concepts(subject_id)
    latest_materials = await study_material_repository.get_latest_materials(
        [concept.id for concept in concepts]
    )
    materials: list[ConceptMaterialResponse] = []
    for concept in concepts:
        material = latest_materials.get(concept.id)
        if not material:
            continue
        if published_only and material.lifecycle_status != MaterialLifecycleStatus.published:
            continue
        materials.append(study_material_service.to_material_response(concept, material))
    return materials


async def query_selected_concept_materials(
    subject_id: str,
    concept_ids: list[str],
) -> list[ConceptMaterialResponse]:
    published_materials = {
        item.concept_id: item
        for item in await list_subject_materials(subject_id, published_only=True)
    }
    missing = [concept_id for concept_id in concept_ids if concept_id not in published_materials]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Published material not available for concept IDs: {missing}",
        )
    return [published_materials[concept_id] for concept_id in concept_ids]


async def get_approved_subject_bundle_path(subject_id: str, owner_id: str) -> Path:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concepts = await study_material_repository.list_concepts(subject_id)
    if not concepts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No concepts found.")
    latest_materials = await study_material_repository.get_latest_materials(
        [concept.id for concept in concepts]
    )
    approved_materials = {
        concept_id: material
        for concept_id, material in latest_materials.items()
        if material.lifecycle_status
        in (MaterialLifecycleStatus.approved, MaterialLifecycleStatus.published)
    }
    if not approved_materials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No approved materials available.",
        )
    concept_name_map = {concept.id: concept.name for concept in concepts}
    settings = get_settings()
    with tempfile.NamedTemporaryFile(
        prefix=f"approved-materials-{subject_id}-",
        suffix=".zip",
        delete=False,
    ) as handle:
        bundle_path = Path(handle.name)
    added = 0
    with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as zf:
        for concept_id, material in approved_materials.items():
            job = await material_job_repository.get_job(material.source_job_id)
            if not job or not job.output_dir:
                continue
            artifact_index = study_material_service.artifact_index_from_json(
                material.artifact_index
            )
            concept_name = concept_name_map.get(concept_id, concept_id)
            concept_slug = _slugify(concept_name)
            folder = f"{concept_slug}-{concept_id[:6]}"
            for field in _BUNDLE_ARTIFACT_FIELDS:
                filename = getattr(artifact_index, field, None)
                if not filename:
                    continue
                relative_path = (
                    f"{job.output_dir}/concepts/{concept_id}/{filename}"
                )
                file_path = settings.material_output_dir / relative_path
                try:
                    file_path = _storage.ensure_local_copy(
                        _storage.material_area,
                        relative_path,
                        local_path=file_path,
                    )
                except FileNotFoundError:
                    continue
                zf.write(file_path, arcname=f"{folder}/{filename}")
                added += 1
    if not added:
        bundle_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approved material files are missing.",
        )
    return bundle_path


async def publish_selected_concepts(
    subject_id: str,
    concept_ids: list[str],
    owner_id: str,
) -> SubjectResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    if not concept_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one concept to publish.",
        )
    concepts = await study_material_repository.list_concepts(subject_id)
    concept_map = {concept.id: concept for concept in concepts}
    unique_ids = list(dict.fromkeys(concept_ids))
    selected: list = []
    invalid_ids: list[str] = []
    for concept_id in unique_ids:
        concept = concept_map.get(concept_id)
        if not concept:
            invalid_ids.append(concept_id)
            continue
        selected.append(concept)
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid concept IDs: {invalid_ids}",
        )
    latest_materials = await study_material_repository.get_latest_materials(
        [concept.id for concept in selected]
    )
    missing = study_material_service.ensure_publishable(selected, latest_materials)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot publish until all selected concepts have approved materials. "
                f"Missing approvals for: {missing}"
            ),
        )
    publish_time = datetime.now(timezone.utc)
    study_material_service.apply_publish_selected(subject, selected, latest_materials, publish_time)
    await study_material_repository.update_subject(subject)
    await study_material_repository.update_concepts(selected)
    await study_material_repository.update_materials(list(latest_materials.values()))
    refreshed_concepts = await study_material_repository.list_concepts(subject_id)
    return study_material_service.to_subject_response(subject, refreshed_concepts)


async def publish_subject(subject_id: str, owner_id: str) -> SubjectResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concepts = await study_material_repository.list_concepts(subject_id)
    if not concepts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish a subject without concepts.",
        )
    latest_materials = await study_material_repository.get_latest_materials(
        [concept.id for concept in concepts]
    )
    missing = study_material_service.ensure_publishable(concepts, latest_materials)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot publish until all concepts have approved materials. Missing approvals for: "
                f"{missing}"
            ),
        )
    publish_time = datetime.now(timezone.utc)
    study_material_service.apply_publish(subject, concepts, latest_materials, publish_time)
    await study_material_repository.update_subject(subject)
    await study_material_repository.update_concepts(concepts)
    await study_material_repository.update_materials(list(latest_materials.values()))
    return study_material_service.to_subject_response(subject, concepts)


async def unpublish_subject(subject_id: str, owner_id: str) -> SubjectResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    if not subject.published:
        return study_material_service.to_subject_response(
            subject, await study_material_repository.list_concepts(subject_id)
        )
    concepts = await study_material_repository.list_concepts(subject_id)
    latest_materials = await study_material_repository.get_latest_materials(
        [concept.id for concept in concepts]
    )
    now = datetime.now(timezone.utc)
    subject.published = False
    subject.updated_at = now
    for concept in concepts:
        if concept.material_status == MaterialLifecycleStatus.published:
            concept.material_status = MaterialLifecycleStatus.approved
    for material in latest_materials.values():
        if material.lifecycle_status == MaterialLifecycleStatus.published:
            material.lifecycle_status = MaterialLifecycleStatus.approved
            material.published_at = None
    await study_material_repository.update_subject(subject)
    await study_material_repository.update_concepts(concepts)
    await study_material_repository.update_materials(list(latest_materials.values()))
    return study_material_service.to_subject_response(subject, concepts)


def _safe_remove_job_outputs(output_root: Path, output_dirs: list[str]) -> None:
    root = output_root.resolve()
    for output_dir in output_dirs:
        if not output_dir or output_dir in (".", ".."):
            continue
        target = (output_root / output_dir).resolve()
        if target == root or not str(target).startswith(str(root)):
            _logger.warning("Skipping unsafe output path: %s", target)
            continue
        try:
            shutil.rmtree(target, ignore_errors=True)
        except OSError as exc:
            _logger.warning("Failed to remove output directory %s: %s", target, exc)


async def delete_subject(subject_id: str, owner_id: str, force: bool = False) -> None:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    jobs = await material_job_repository.list_jobs(subject_id, owner_id=owner_id)
    if any(job.status in (JobStatus.queued, JobStatus.running) for job in jobs) and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a subject while generation jobs are running.",
        )
    output_dirs = [job.output_dir for job in jobs if job.output_dir]
    await study_material_repository.delete_subject_data(subject_id)
    settings = get_settings()
    _safe_remove_job_outputs(settings.material_output_dir, output_dirs)
    for output_dir in output_dirs:
        _storage.delete_prefix(_storage.material_area, output_dir)


async def get_admin_concept_learning_content(
    subject_id: str,
    concept_id: str,
    owner_id: str,
) -> LearningContentResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    material = await study_material_repository.get_latest_material(concept_id)
    if not material or not material.content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learning content not available.")
    return study_material_service.to_learning_content_response(subject, concept, material)


async def get_student_concept_learning_content(
    subject_id: str,
    concept_id: str,
) -> LearningContentResponse:
    subject = await study_material_repository.get_subject(subject_id)
    if not subject or not subject.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject is not published.")
    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    material = await study_material_repository.get_latest_material(
        concept_id, published_only=True
    )
    if not material or not material.content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learning content not available.")
    return study_material_service.to_learning_content_response(subject, concept, material)


async def update_admin_concept_learning_content(
    subject_id: str,
    concept_id: str,
    payload: LearningContentUpdate,
    owner_id: str,
) -> LearningContentResponse:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    material = await study_material_repository.get_latest_material(concept_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learning content not found.")
    if material.lifecycle_status == MaterialLifecycleStatus.published:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unpublish before editing published learning content.",
        )
    material.content = payload.content.model_dump()
    material.content_text = learning_content_service.build_search_text(payload.content)
    material.content_schema_version = learning_content_service.CONTENT_SCHEMA_VERSION
    material.updated_at = datetime.now(timezone.utc)
    await study_material_repository.update_materials([material])
    return study_material_service.to_learning_content_response(subject, concept, material)


async def list_student_bookmarks(
    user_id: str,
    subject_id: str | None = None,
) -> list[ConceptBookmarkResponse]:
    bookmarks = await study_material_repository.list_bookmarks(user_id, subject_id)
    responses: list[ConceptBookmarkResponse] = []
    for bookmark in bookmarks:
        concept = await study_material_repository.get_concept(bookmark.concept_id)
        if not concept:
            continue
        subject = await study_material_repository.get_subject(concept.subject_id)
        if not subject or not subject.published:
            continue
        responses.append(
            ConceptBookmarkResponse(
                concept_id=concept.id,
                concept_name=concept.name,
                subject_id=subject.id,
                subject_name=subject.name,
                created_at=bookmark.created_at,
            )
        )
    return responses


async def add_student_bookmark(user_id: str, subject_id: str, concept_id: str) -> None:
    subject = await study_material_repository.get_subject(subject_id)
    if not subject or not subject.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject is not published.")
    enrollment = await study_material_repository.get_subject_enrollment(user_id, subject_id)
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your administrator must assign this syllabus before bookmarking topics.",
        )
    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    material = await study_material_repository.get_latest_material(concept_id, published_only=True)
    if not material or material.lifecycle_status != MaterialLifecycleStatus.published:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Concept is not published yet.")
    await study_material_repository.create_bookmark(user_id, concept_id)


async def remove_student_bookmark(user_id: str, concept_id: str) -> None:
    await study_material_repository.delete_bookmark(user_id, concept_id)


async def get_subject_record(subject_id: str) -> SubjectRecord:
    subject = await study_material_repository.get_subject(subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concepts = await study_material_repository.list_concepts(subject_id)
    latest_materials = await study_material_repository.get_latest_materials(
        [concept.id for concept in concepts]
    )
    return study_material_service.to_subject_record(subject, concepts, latest_materials)
