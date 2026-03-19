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
        prompt_text=asset.prompt_text,
        focus_area=asset.focus_area,
        complexity_level=asset.complexity_level,
        visual_style=asset.visual_style,
        generator_name=asset.generator_name,
        explanation=asset.explanation,
        learning_points=list(asset.learning_points or []),
        width=asset.width,
        height=asset.height,
        mime_type=asset.mime_type,
        pedagogical_score=round(float(asset.relevance_score or 0.0), 4),
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
    latest_asset = max(assets, key=lambda item: item.created_at) if assets else None
    return ConceptImageCollectionResponse(
        subject_id=subject.id,
        subject_name=subject.name,
        concept_id=concept.id,
        concept_name=concept.name,
        material_version=material.version,
        prompt_text=latest_asset.prompt_text if latest_asset else None,
        focus_area=latest_asset.focus_area if latest_asset else None,
        complexity_level=latest_asset.complexity_level if latest_asset else None,
        images=[to_image_asset_response(asset) for asset in assets],
    )


def resolve_storage_path(base_dir: Path, relative_path: str) -> Path:
    target = (base_dir / relative_path).resolve()
    base = base_dir.resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Unsafe image path.")
    return target
