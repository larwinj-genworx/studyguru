from __future__ import annotations

from sqlalchemy import desc, select

from src.data.clients.postgres import AsyncSessionFactory
from src.data.models.postgres.models import Concept, ConceptMaterial, Subject
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
                db_material.published_at = material.published_at
