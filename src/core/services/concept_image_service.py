from __future__ import annotations

from pathlib import Path

from src.data.models.postgres.models import Concept, ConceptImageAsset, ConceptMaterial, Subject
from src.schemas.concept_images import ConceptImageAssetResponse, ConceptImageCollectionResponse


def to_image_asset_response(asset: ConceptImageAsset) -> ConceptImageAssetResponse:
    return ConceptImageAssetResponse(
        image_id=asset.id,
        status=asset.status,
        title=asset.title,
        caption=asset.caption,
        alt_text=asset.alt_text,
        intent_label=asset.intent_label,
        source_page_url=asset.source_page_url,
        source_image_url=asset.source_image_url,
        source_domain=asset.source_domain,
        width=asset.width,
        height=asset.height,
        mime_type=asset.mime_type,
        relevance_score=round(float(asset.relevance_score or 0.0), 4),
        created_at=asset.created_at,
        approved_at=asset.approved_at,
    )


def to_image_collection_response(
    *,
    subject: Subject,
    concept: Concept,
    material: ConceptMaterial,
    assets: list[ConceptImageAsset],
) -> ConceptImageCollectionResponse:
    return ConceptImageCollectionResponse(
        subject_id=subject.id,
        subject_name=subject.name,
        concept_id=concept.id,
        concept_name=concept.name,
        material_version=material.version,
        images=[to_image_asset_response(asset) for asset in assets],
    )


def resolve_storage_path(base_dir: Path, relative_path: str) -> Path:
    target = (base_dir / relative_path).resolve()
    base = base_dir.resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Unsafe image path.")
    return target
