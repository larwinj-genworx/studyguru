from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status

from src.core.services import study_material_service, learning_content_service
from src.data.repositories import study_material_repository
from src.schemas.study_material import (
    ConceptBulkCreate,
    ConceptMaterialResponse,
    ConceptResponse,
    ConceptBookmarkResponse,
    LearningContentResponse,
    LearningContentUpdate,
    MaterialLifecycleStatus,
    SubjectCreate,
    SubjectRecord,
    SubjectResponse,
)


async def create_subject(payload: SubjectCreate, owner_id: str) -> SubjectResponse:
    subject = study_material_service.build_subject(payload, owner_id)
    subject = await study_material_repository.create_subject(subject)
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
    concepts = [
        study_material_service.build_concept(concept, subject_id)
        for concept in payload.concepts
    ]
    subject.updated_at = datetime.now(timezone.utc)
    await study_material_repository.add_concepts(concepts)
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
