from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path

from fastapi import HTTPException, status

from src.config.settings import get_settings
from src.core.services import concept_image_service, learning_content_service
from src.core.services.concept_visual_microservice_client import ConceptVisualMicroserviceClient
from src.data.models.postgres.models import ConceptImageAsset
from src.data.repositories import concept_image_repository, study_material_repository
from src.schemas.concept_visual_microservice import ConceptVisualRenderRequest
from src.schemas.concept_images import ConceptImageCollectionResponse, ConceptImageStatus
from src.schemas.study_material import LearningContent, MaterialLifecycleStatus

_settings = get_settings()
_client = ConceptVisualMicroserviceClient(_settings)
_logger = logging.getLogger(__name__)
_LOCAL_MICROSERVICE_OUTPUT_DIR = Path(__file__).resolve().parents[4] / "ConceptVisualBackend" / "output" / "concept_visuals"


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
    prompt: str | None = None,
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
            _remove_paths(asset.local_image_path, asset.thumbnail_path)
        await concept_image_repository.delete_image_assets([asset.id for asset in removable])

    max_variants = max(1, min(_settings.concept_image_max_candidates, 4))
    if max_variants != _settings.concept_image_max_candidates:
        _logger.warning(
            "Clamped CONCEPT_IMAGE_MAX_CANDIDATES from %s to %s to satisfy the concept visual service contract.",
            _settings.concept_image_max_candidates,
            max_variants,
        )

    rendered = await _client.render(
        ConceptVisualRenderRequest(
            subject_id=subject.id,
            subject_name=subject.name,
            grade_level=subject.grade_level,
            concept_id=concept.id,
            concept_name=concept.name,
            concept_description=concept.description,
            concept_material_id=material.id,
            prompt=prompt,
            max_variants=max_variants,
            content=content,
        )
    )
    now = datetime.now(timezone.utc)
    assets = [
        ConceptImageAsset(
            subject_id=subject.id,
            concept_id=concept.id,
            concept_material_id=material.id,
            status=ConceptImageStatus.pending,
            title=item.title,
            caption=item.caption,
            alt_text=item.alt_text,
            intent_label=item.visual_style,
            prompt_text=rendered.prompt,
            focus_area=item.focus_area,
            complexity_level=item.complexity_level,
            visual_style=item.visual_style,
            generator_name=item.generator_name,
            explanation=item.explanation,
            learning_points=item.learning_points,
            render_spec=item.render_spec,
            local_image_path=item.relative_image_path,
            thumbnail_path=item.relative_thumbnail_path,
            mime_type=item.mime_type,
            width=item.width,
            height=item.height,
            file_size_bytes=item.file_size_bytes,
            fingerprint=item.fingerprint,
            relevance_score=item.pedagogical_score,
            created_at=now,
            updated_at=now,
        )
        for item in rendered.assets
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
    path = _resolve_existing_storage_path(relative_path)
    if path is None:
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
    path = _resolve_existing_storage_path(relative_path)
    if path is None:
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


def _remove_paths(*relative_paths: str | None) -> None:
    for relative_path in relative_paths:
        if not relative_path:
            continue
        for base_dir in _image_storage_roots():
            try:
                target = concept_image_service.resolve_storage_path(
                    base_dir,
                    relative_path,
                )
            except ValueError:
                continue
            if target.exists():
                target.unlink(missing_ok=True)


def _resolve_existing_storage_path(relative_path: str) -> Path | None:
    for base_dir in _image_storage_roots():
        try:
            candidate = concept_image_service.resolve_storage_path(base_dir, relative_path)
        except ValueError:
            continue
        if candidate.exists():
            return candidate
    return None


def _image_storage_roots() -> list[Path]:
    roots: list[Path] = []
    for base_dir in (_settings.concept_visual_output_dir, _LOCAL_MICROSERVICE_OUTPUT_DIR):
        resolved = base_dir.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return roots
