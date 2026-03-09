from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from src.config.settings import get_settings
from src.control.concept_image_curation.services import ConceptImageCurationEngine
from src.control.concept_image_curation.storage import ConceptImageStorageService
from src.core.services import concept_image_service, learning_content_service
from src.data.models.postgres.models import ConceptImageAsset
from src.data.repositories import concept_image_repository, study_material_repository
from src.schemas.concept_images import ConceptImageCollectionResponse, ConceptImageStatus
from src.schemas.study_material import LearningContent, MaterialLifecycleStatus


logger = logging.getLogger("uvicorn.error")

_settings = get_settings()
_engine: ConceptImageCurationEngine | None = None
_storage = ConceptImageStorageService(_settings)


def _ensure_engine() -> ConceptImageCurationEngine:
    global _engine
    if _engine is not None:
        return _engine
    _engine = ConceptImageCurationEngine(_settings)
    return _engine


async def get_admin_concept_images(
    *,
    subject_id: str,
    concept_id: str,
    owner_id: str,
) -> ConceptImageCollectionResponse:
    subject, concept, material, _content = await _get_admin_material_context(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=owner_id,
    )
    assets = await concept_image_repository.list_images_for_material(material.id)
    return concept_image_service.to_image_collection_response(
        subject=subject,
        concept=concept,
        material=material,
        assets=assets,
    )


async def generate_admin_concept_images(
    *,
    subject_id: str,
    concept_id: str,
    owner_id: str,
    refresh: bool = False,
) -> ConceptImageCollectionResponse:
    subject, concept, material, content = await _get_admin_material_context(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=owner_id,
    )
    existing = await concept_image_repository.list_images_for_material(material.id)
    if existing and not refresh:
        return concept_image_service.to_image_collection_response(
            subject=subject,
            concept=concept,
            material=material,
            assets=existing,
        )

    removable = [asset for asset in existing if asset.status != ConceptImageStatus.approved]
    if removable:
        for asset in removable:
            _storage.remove_paths(asset.local_image_path, asset.thumbnail_path)
        await concept_image_repository.delete_image_assets([asset.id for asset in removable])

    approved_existing = [asset for asset in existing if asset.status == ConceptImageStatus.approved]
    fingerprints = {asset.fingerprint for asset in approved_existing if asset.fingerprint}

    engine = _ensure_engine()
    curated = await engine.curate(
        subject_id=subject.id,
        subject_name=subject.name,
        grade_level=subject.grade_level,
        concept_name=concept.name,
        concept_description=concept.description,
        concept_material_id=material.id,
        content=content,
        existing_fingerprints=fingerprints,
    )
    now = datetime.now(timezone.utc)
    assets = [
        ConceptImageAsset(
            subject_id=subject.id,
            concept_id=concept.id,
            concept_material_id=material.id,
            status=ConceptImageStatus.pending,
            title=item.candidate.title,
            caption=item.candidate.caption,
            alt_text=item.candidate.alt_text,
            intent_label=item.candidate.intent_label,
            source_page_url=item.candidate.source_page_url,
            source_image_url=item.candidate.source_image_url,
            source_domain=item.candidate.source_domain,
            local_image_path=item.stored.relative_image_path,
            thumbnail_path=item.stored.relative_thumbnail_path,
            mime_type=item.stored.mime_type,
            width=item.stored.width,
            height=item.stored.height,
            file_size_bytes=item.stored.file_size_bytes,
            fingerprint=item.stored.fingerprint,
            relevance_score=item.candidate.relevance_score,
            created_at=now,
            updated_at=now,
        )
        for item in curated
    ]
    if assets:
        await concept_image_repository.create_image_assets(assets)

    current = await concept_image_repository.list_images_for_material(material.id)
    return concept_image_service.to_image_collection_response(
        subject=subject,
        concept=concept,
        material=material,
        assets=current,
    )


async def approve_admin_concept_image(
    *,
    subject_id: str,
    concept_id: str,
    image_id: str,
    owner_id: str,
) -> ConceptImageCollectionResponse:
    subject, concept, material, _content = await _get_admin_material_context(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=owner_id,
    )
    asset = await _get_admin_image_asset(
        subject_id=subject.id,
        concept_id=concept.id,
        image_id=image_id,
    )
    asset.status = ConceptImageStatus.approved
    asset.approved_at = datetime.now(timezone.utc)
    await concept_image_repository.update_image_asset(asset)
    assets = await concept_image_repository.list_images_for_material(material.id)
    return concept_image_service.to_image_collection_response(
        subject=subject,
        concept=concept,
        material=material,
        assets=assets,
    )


async def reject_admin_concept_image(
    *,
    subject_id: str,
    concept_id: str,
    image_id: str,
    owner_id: str,
) -> ConceptImageCollectionResponse:
    subject, concept, material, _content = await _get_admin_material_context(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=owner_id,
    )
    asset = await _get_admin_image_asset(
        subject_id=subject.id,
        concept_id=concept.id,
        image_id=image_id,
    )
    asset.status = ConceptImageStatus.rejected
    asset.approved_at = None
    await concept_image_repository.update_image_asset(asset)
    assets = await concept_image_repository.list_images_for_material(material.id)
    return concept_image_service.to_image_collection_response(
        subject=subject,
        concept=concept,
        material=material,
        assets=assets,
    )


async def get_admin_concept_image_file_path(
    *,
    subject_id: str,
    concept_id: str,
    image_id: str,
    owner_id: str,
    variant: str = "full",
) -> Path:
    subject, concept, _material, _content = await _get_admin_material_context(
        subject_id=subject_id,
        concept_id=concept_id,
        owner_id=owner_id,
    )
    asset = await _get_admin_image_asset(
        subject_id=subject.id,
        concept_id=concept.id,
        image_id=image_id,
    )
    relative_path = asset.thumbnail_path if variant == "thumb" else asset.local_image_path
    try:
        path = concept_image_service.resolve_storage_path(_settings.concept_image_output_dir, relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found.")
    return path


async def list_student_concept_images(
    *,
    subject_id: str,
    concept_id: str,
) -> ConceptImageCollectionResponse:
    subject, concept, material, _content = await _get_student_material_context(
        subject_id=subject_id,
        concept_id=concept_id,
    )
    assets = await concept_image_repository.list_images_for_material(
        material.id,
        status=ConceptImageStatus.approved,
    )
    return concept_image_service.to_image_collection_response(
        subject=subject,
        concept=concept,
        material=material,
        assets=assets,
    )


async def get_student_concept_image_file_path(
    *,
    subject_id: str,
    concept_id: str,
    image_id: str,
    variant: str = "full",
) -> Path:
    subject, concept, material, _content = await _get_student_material_context(
        subject_id=subject_id,
        concept_id=concept_id,
    )
    asset = await concept_image_repository.get_image_asset(image_id)
    if not asset or asset.subject_id != subject.id or asset.concept_id != concept.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    if asset.concept_material_id != material.id or asset.status != ConceptImageStatus.approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approved image not found.")
    relative_path = asset.thumbnail_path if variant == "thumb" else asset.local_image_path
    try:
        path = concept_image_service.resolve_storage_path(_settings.concept_image_output_dir, relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image file not found.")
    return path


async def _get_admin_material_context(
    *,
    subject_id: str,
    concept_id: str,
    owner_id: str,
) -> tuple:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    material = await study_material_repository.get_latest_material(concept_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    if not material.content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learning content not available.")
    content = learning_content_service.normalize_learning_content(
        LearningContent(**material.content)
    )
    return subject, concept, material, content


async def _get_student_material_context(
    *,
    subject_id: str,
    concept_id: str,
) -> tuple:
    subject = await study_material_repository.get_subject(subject_id)
    if not subject or not subject.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject is not published.")
    concept = await study_material_repository.get_concept(concept_id)
    if not concept or concept.subject_id != subject.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    material = await study_material_repository.get_latest_material(concept_id, published_only=True)
    if not material or material.lifecycle_status != MaterialLifecycleStatus.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Published material not available.")
    if not material.content:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Learning content not available.")
    content = learning_content_service.normalize_learning_content(
        LearningContent(**material.content)
    )
    return subject, concept, material, content


async def _get_admin_image_asset(
    *,
    subject_id: str,
    concept_id: str,
    image_id: str,
) -> ConceptImageAsset:
    asset = await concept_image_repository.get_image_asset(image_id)
    if not asset or asset.subject_id != subject_id or asset.concept_id != concept_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found.")
    return asset
