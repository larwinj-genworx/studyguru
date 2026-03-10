from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, desc, select

from src.data.clients.postgres import AsyncSessionFactory
from src.data.models.postgres.models import ConceptImageAsset
from src.schemas.concept_images import ConceptImageStatus


async def list_images_for_material(
    concept_material_id: str,
    status: ConceptImageStatus | None = None,
) -> list[ConceptImageAsset]:
    async with AsyncSessionFactory() as session:
        stmt = (
            select(ConceptImageAsset)
            .where(ConceptImageAsset.concept_material_id == concept_material_id)
            .order_by(desc(ConceptImageAsset.relevance_score), desc(ConceptImageAsset.created_at))
        )
        if status is not None:
            stmt = stmt.where(ConceptImageAsset.status == status)
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_image_asset(image_id: str) -> ConceptImageAsset | None:
    async with AsyncSessionFactory() as session:
        return await session.get(ConceptImageAsset, image_id)


async def create_image_assets(assets: list[ConceptImageAsset]) -> list[ConceptImageAsset]:
    if not assets:
        return []
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add_all(assets)
        return assets


async def update_image_asset(asset: ConceptImageAsset) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            db_asset = await session.get(ConceptImageAsset, asset.id)
            if not db_asset:
                return
            db_asset.status = asset.status
            db_asset.title = asset.title
            db_asset.caption = asset.caption
            db_asset.alt_text = asset.alt_text
            db_asset.intent_label = asset.intent_label
            db_asset.prompt_text = asset.prompt_text
            db_asset.focus_area = asset.focus_area
            db_asset.complexity_level = asset.complexity_level
            db_asset.visual_style = asset.visual_style
            db_asset.generator_name = asset.generator_name
            db_asset.explanation = asset.explanation
            db_asset.learning_points = asset.learning_points
            db_asset.render_spec = asset.render_spec
            db_asset.source_page_url = asset.source_page_url
            db_asset.source_image_url = asset.source_image_url
            db_asset.source_domain = asset.source_domain
            db_asset.local_image_path = asset.local_image_path
            db_asset.thumbnail_path = asset.thumbnail_path
            db_asset.mime_type = asset.mime_type
            db_asset.width = asset.width
            db_asset.height = asset.height
            db_asset.file_size_bytes = asset.file_size_bytes
            db_asset.fingerprint = asset.fingerprint
            db_asset.relevance_score = asset.relevance_score
            db_asset.approved_at = asset.approved_at
            db_asset.updated_at = datetime.now(timezone.utc)


async def delete_image_assets(image_ids: list[str]) -> None:
    if not image_ids:
        return
    async with AsyncSessionFactory() as session:
        async with session.begin():
            await session.execute(
                delete(ConceptImageAsset).where(ConceptImageAsset.id.in_(image_ids))
            )
