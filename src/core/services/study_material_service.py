from __future__ import annotations

from datetime import datetime

from src.data.models.postgres.models import Concept, ConceptMaterial, Subject
from src.core.services import learning_content_service
from src.schemas.study_material import (
    ArtifactIndex,
    ConceptBulkCreate,
    ConceptCreate,
    ConceptMaterialRecord,
    ConceptMaterialResponse,
    ConceptResponse,
    LearningContent,
    LearningContentResponse,
    MaterialLifecycleStatus,
    SubjectCreate,
    SubjectRecord,
    SubjectResponse,
)


def artifact_index_from_json(payload: dict | None) -> ArtifactIndex:
    if not payload:
        return ArtifactIndex()
    return ArtifactIndex(**payload)


def artifact_index_to_json(index: ArtifactIndex | None) -> dict:
    if not index:
        return {}
    return index.model_dump(exclude_none=True)


def build_subject(payload: SubjectCreate, owner_id: str) -> Subject:
    return Subject(
        owner_id=owner_id,
        name=payload.name.strip(),
        grade_level=payload.grade_level.strip(),
        description=payload.description,
        published=False,
    )


def build_concept(payload: ConceptCreate, subject_id: str) -> Concept:
    return Concept(
        subject_id=subject_id,
        name=payload.name.strip(),
        description=payload.description,
        material_status=MaterialLifecycleStatus.unavailable,
        material_version=0,
    )


def ensure_publishable(concepts: list[Concept], latest_materials: dict[str, ConceptMaterial]) -> list[str]:
    missing: list[str] = []
    for concept in concepts:
        material = latest_materials.get(concept.id)
        if not material or material.lifecycle_status not in (
            MaterialLifecycleStatus.approved,
            MaterialLifecycleStatus.published,
        ):
            missing.append(concept.name)
    return missing


def apply_publish(
    subject: Subject,
    concepts: list[Concept],
    latest_materials: dict[str, ConceptMaterial],
    publish_time: datetime,
) -> None:
    subject.published = True
    subject.updated_at = publish_time
    concept_map = {concept.id: concept for concept in concepts}
    for concept_id, material in latest_materials.items():
        material.lifecycle_status = MaterialLifecycleStatus.published
        material.published_at = publish_time
        concept = concept_map.get(concept_id)
        if concept:
            concept.material_status = MaterialLifecycleStatus.published
            concept.material_version = material.version


def apply_publish_selected(
    subject: Subject,
    concepts: list[Concept],
    latest_materials: dict[str, ConceptMaterial],
    publish_time: datetime,
) -> None:
    subject.published = True
    subject.updated_at = publish_time
    concept_map = {concept.id: concept for concept in concepts}
    for concept_id, material in latest_materials.items():
        concept = concept_map.get(concept_id)
        if not concept:
            continue
        if material.lifecycle_status != MaterialLifecycleStatus.published:
            material.lifecycle_status = MaterialLifecycleStatus.published
        if material.published_at is None:
            material.published_at = publish_time
        if concept.material_status != MaterialLifecycleStatus.published:
            concept.material_status = MaterialLifecycleStatus.published
        concept.material_version = material.version


def to_concept_response(concept: Concept) -> ConceptResponse:
    return ConceptResponse(
        concept_id=concept.id,
        name=concept.name,
        description=concept.description,
        created_at=concept.created_at,
        material_status=concept.material_status,
        material_version=concept.material_version,
    )


def to_subject_response(subject: Subject, concepts: list[Concept]) -> SubjectResponse:
    return SubjectResponse(
        subject_id=subject.id,
        name=subject.name,
        grade_level=subject.grade_level,
        description=subject.description,
        published=subject.published,
        created_at=subject.created_at,
        updated_at=subject.updated_at,
        concepts=[to_concept_response(concept) for concept in concepts],
    )


def to_material_response(concept: Concept, material: ConceptMaterial) -> ConceptMaterialResponse:
    return ConceptMaterialResponse(
        concept_id=concept.id,
        concept_name=concept.name,
        lifecycle_status=material.lifecycle_status,
        version=material.version,
        source_job_id=material.source_job_id,
        artifact_index=artifact_index_from_json(material.artifact_index),
        generated_at=material.generated_at,
        approved_at=material.approved_at,
        published_at=material.published_at,
    )


def to_learning_content_response(
    subject: Subject,
    concept: Concept,
    material: ConceptMaterial,
) -> LearningContentResponse:
    content_payload = material.content or {}
    if not isinstance(content_payload, dict):
        content_payload = {}
    content = LearningContent(**content_payload) if content_payload else LearningContent()
    content = learning_content_service.normalize_learning_content(content)
    return LearningContentResponse(
        concept_id=concept.id,
        concept_name=concept.name,
        subject_id=subject.id,
        subject_name=subject.name,
        grade_level=subject.grade_level,
        lifecycle_status=material.lifecycle_status,
        version=material.version,
        generated_at=material.generated_at,
        approved_at=material.approved_at,
        published_at=material.published_at,
        content_schema_version=material.content_schema_version,
        content=content,
    )


def to_subject_record(
    subject: Subject,
    concepts: list[Concept],
    latest_materials: dict[str, ConceptMaterial],
) -> SubjectRecord:
    concept_meta = {concept.id: to_concept_response(concept) for concept in concepts}
    materials: dict[str, ConceptMaterialRecord] = {}
    for concept in concepts:
        material = latest_materials.get(concept.id)
        if not material:
            continue
        materials[concept.id] = ConceptMaterialRecord(
            concept_id=concept.id,
            concept_name=concept.name,
            lifecycle_status=material.lifecycle_status,
            version=material.version,
            source_job_id=material.source_job_id,
            artifact_index=artifact_index_from_json(material.artifact_index),
            generated_at=material.generated_at,
            approved_at=material.approved_at,
            published_at=material.published_at,
        )
    return SubjectRecord(
        subject_id=subject.id,
        name=subject.name,
        grade_level=subject.grade_level,
        description=subject.description,
        published=subject.published,
        created_at=subject.created_at,
        updated_at=subject.updated_at,
        concept_meta=concept_meta,
        materials=materials,
    )
