from __future__ import annotations

from sqlalchemy import delete, desc, select
from datetime import datetime, timezone

from src.data.clients.postgres import AsyncSessionFactory
from src.data.models.postgres.models import (
    Concept,
    ConceptBookmark,
    ConceptMaterial,
    ConceptVideoFeedback,
    MaterialJob,
    MaterialJobConcept,
    Subject,
)
from src.schemas.study_material import MaterialLifecycleStatus


async def create_subject(subject: Subject) -> Subject:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add(subject)
        return subject


async def get_subject(subject_id: str) -> Subject | None:
    async with AsyncSessionFactory() as session:
        return await session.get(Subject, subject_id)


async def get_subject_for_owner(subject_id: str, owner_id: str) -> Subject | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Subject).where(Subject.id == subject_id, Subject.owner_id == owner_id)
        )
        return result.scalar_one_or_none()


async def list_subjects(published_only: bool = False) -> list[Subject]:
    async with AsyncSessionFactory() as session:
        stmt = select(Subject)
        if published_only:
            stmt = stmt.where(Subject.published.is_(True))
        stmt = stmt.order_by(desc(Subject.created_at))
        result = await session.execute(stmt)
        return result.scalars().all()


async def list_subjects_for_owner(owner_id: str) -> list[Subject]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Subject)
            .where(Subject.owner_id == owner_id)
            .order_by(desc(Subject.created_at))
        )
        return result.scalars().all()


async def list_concepts(subject_id: str) -> list[Concept]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Concept).where(Concept.subject_id == subject_id).order_by(Concept.created_at)
        )
        return result.scalars().all()


async def get_concept(concept_id: str) -> Concept | None:
    async with AsyncSessionFactory() as session:
        return await session.get(Concept, concept_id)


async def add_concepts(concepts: list[Concept]) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add_all(concepts)


async def update_subject(subject: Subject) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            db_subject = await session.get(Subject, subject.id)
            if not db_subject:
                return
            db_subject.name = subject.name
            db_subject.grade_level = subject.grade_level
            db_subject.description = subject.description
            db_subject.published = subject.published
            db_subject.updated_at = subject.updated_at


async def update_concepts(concepts: list[Concept]) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            for concept in concepts:
                db_concept = await session.get(Concept, concept.id)
                if not db_concept:
                    continue
                db_concept.material_status = concept.material_status
                db_concept.material_version = concept.material_version


async def get_latest_materials(concept_ids: list[str]) -> dict[str, ConceptMaterial]:
    if not concept_ids:
        return {}
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(ConceptMaterial)
            .where(ConceptMaterial.concept_id.in_(concept_ids))
            .order_by(desc(ConceptMaterial.version))
        )
        rows = result.scalars().all()
        latest: dict[str, ConceptMaterial] = {}
        for material in rows:
            if material.concept_id not in latest:
                latest[material.concept_id] = material
        return latest


async def get_latest_material(concept_id: str, published_only: bool = False) -> ConceptMaterial | None:
    async with AsyncSessionFactory() as session:
        stmt = select(ConceptMaterial).where(ConceptMaterial.concept_id == concept_id)
        if published_only:
            stmt = stmt.where(ConceptMaterial.lifecycle_status == MaterialLifecycleStatus.published)
        stmt = stmt.order_by(desc(ConceptMaterial.version))
        result = await session.execute(stmt)
        return result.scalars().first()


async def get_materials_for_job(job_id: str, concept_ids: list[str]) -> dict[str, ConceptMaterial]:
    if not concept_ids:
        return {}
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(ConceptMaterial).where(
                ConceptMaterial.source_job_id == job_id,
                ConceptMaterial.concept_id.in_(concept_ids),
            )
        )
        rows = result.scalars().all()
        return {row.concept_id: row for row in rows}


async def create_concept_materials(materials: list[ConceptMaterial]) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add_all(materials)


async def update_materials(materials: list[ConceptMaterial]) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            for material in materials:
                db_material = await session.get(ConceptMaterial, material.id)
                if not db_material:
                    continue
                db_material.lifecycle_status = material.lifecycle_status
                if material.published_at is not None or material.lifecycle_status != MaterialLifecycleStatus.published:
                    db_material.published_at = material.published_at
                if material.approved_at is not None:
                    db_material.approved_at = material.approved_at
                if material.artifact_index is not None:
                    db_material.artifact_index = material.artifact_index
                if material.content is not None:
                    db_material.content = material.content
                if material.content_text is not None:
                    db_material.content_text = material.content_text
                if material.content_schema_version is not None:
                    db_material.content_schema_version = material.content_schema_version
                db_material.updated_at = datetime.now(timezone.utc)


async def list_bookmarks(user_id: str, subject_id: str | None = None) -> list[ConceptBookmark]:
    async with AsyncSessionFactory() as session:
        stmt = select(ConceptBookmark).where(ConceptBookmark.user_id == user_id)
        if subject_id:
            stmt = stmt.join(Concept, Concept.id == ConceptBookmark.concept_id).where(
                Concept.subject_id == subject_id
            )
        result = await session.execute(stmt)
        return result.scalars().all()


async def create_bookmark(user_id: str, concept_id: str) -> ConceptBookmark:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            existing = await session.get(
                ConceptBookmark,
                {"user_id": user_id, "concept_id": concept_id},
            )
            if existing:
                return existing
            bookmark = ConceptBookmark(user_id=user_id, concept_id=concept_id)
            session.add(bookmark)
        return bookmark


async def delete_bookmark(user_id: str, concept_id: str) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            row = await session.get(
                ConceptBookmark,
                {"user_id": user_id, "concept_id": concept_id},
            )
            if row:
                await session.delete(row)


async def list_video_feedback(concept_id: str, status: str | None = None) -> list[ConceptVideoFeedback]:
    async with AsyncSessionFactory() as session:
        stmt = select(ConceptVideoFeedback).where(ConceptVideoFeedback.concept_id == concept_id)
        if status:
            stmt = stmt.where(ConceptVideoFeedback.status == status)
        result = await session.execute(stmt)
        return result.scalars().all()


async def upsert_video_feedback(concept_id: str, video_id: str, status: str) -> ConceptVideoFeedback:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            row = await session.get(
                ConceptVideoFeedback,
                {"concept_id": concept_id, "video_id": video_id},
            )
            if row:
                row.status = status
                return row
            row = ConceptVideoFeedback(
                concept_id=concept_id,
                video_id=video_id,
                status=status,
            )
            session.add(row)
            return row


async def delete_subject_data(subject_id: str) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            concept_rows = await session.execute(
                select(Concept.id).where(Concept.subject_id == subject_id)
            )
            concept_ids = [row[0] for row in concept_rows.fetchall()]

            job_rows = await session.execute(
                select(MaterialJob.id).where(MaterialJob.subject_id == subject_id)
            )
            job_ids = [row[0] for row in job_rows.fetchall()]

            if job_ids:
                await session.execute(
                    delete(ConceptMaterial).where(ConceptMaterial.source_job_id.in_(job_ids))
                )

            if concept_ids:
                await session.execute(
                    delete(ConceptBookmark).where(ConceptBookmark.concept_id.in_(concept_ids))
                )
                await session.execute(
                    delete(ConceptVideoFeedback).where(ConceptVideoFeedback.concept_id.in_(concept_ids))
                )
                await session.execute(
                    delete(MaterialJobConcept).where(MaterialJobConcept.concept_id.in_(concept_ids))
                )
                await session.execute(
                    delete(ConceptMaterial).where(ConceptMaterial.concept_id.in_(concept_ids))
                )
                await session.execute(delete(Concept).where(Concept.id.in_(concept_ids)))

            await session.execute(delete(ConceptMaterial).where(ConceptMaterial.subject_id == subject_id))

            if job_ids:
                await session.execute(
                    delete(MaterialJobConcept).where(MaterialJobConcept.job_id.in_(job_ids))
                )
                await session.execute(delete(MaterialJob).where(MaterialJob.id.in_(job_ids)))

            await session.execute(delete(Subject).where(Subject.id == subject_id))
