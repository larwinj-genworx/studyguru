from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select

from src.data.clients.postgres import AsyncSessionFactory
from src.data.models.postgres.models import Concept, MaterialJob, MaterialJobConcept, Subject


async def create_job(job: MaterialJob, concept_ids: list[str]) -> MaterialJob:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add(job)
            await session.flush()
            session.add_all(
                [
                    MaterialJobConcept(
                        job_id=job.id,
                        concept_id=concept_id,
                        status="queued",
                        artifact_index={},
                    )
                    for concept_id in concept_ids
                ]
            )
        return job


async def get_job(job_id: str) -> MaterialJob | None:
    async with AsyncSessionFactory() as session:
        return await session.get(MaterialJob, job_id)


async def list_jobs(subject_id: str | None = None, owner_id: str | None = None) -> list[MaterialJob]:
    async with AsyncSessionFactory() as session:
        stmt = select(MaterialJob).order_by(desc(MaterialJob.created_at))
        if subject_id:
            stmt = stmt.where(MaterialJob.subject_id == subject_id)
        if owner_id:
            stmt = stmt.join(Subject, Subject.id == MaterialJob.subject_id).where(
                Subject.owner_id == owner_id
            )
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_job_concepts(job_id: str) -> list[MaterialJobConcept]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(MaterialJobConcept)
            .where(MaterialJobConcept.job_id == job_id)
            .order_by(MaterialJobConcept.created_at)
        )
        return result.scalars().all()


async def update_job(job: MaterialJob) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            db_job = await session.get(MaterialJob, job.id)
            if not db_job:
                return
            db_job.status = job.status
            db_job.review_status = job.review_status
            db_job.progress = job.progress
            db_job.artifact_index = job.artifact_index
            db_job.errors = job.errors
            db_job.reviewer_note = job.reviewer_note
            db_job.updated_at = job.updated_at
            db_job.reviewed_at = job.reviewed_at
            db_job.output_dir = job.output_dir
            db_job.revision_note = job.revision_note
            db_job.learner_profile = job.learner_profile


async def update_job_concepts(job_id: str, concept_updates: dict[str, dict]) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            for concept_id, values in concept_updates.items():
                row = await session.get(
                    MaterialJobConcept,
                    {"job_id": job_id, "concept_id": concept_id},
                )
                if not row:
                    row = MaterialJobConcept(
                        job_id=job_id,
                        concept_id=concept_id,
                        status="queued",
                        artifact_index={},
                    )
                    session.add(row)
                if "status" in values:
                    row.status = values["status"]
                if "artifact_index" in values:
                    row.artifact_index = values["artifact_index"]
                row.updated_at = datetime.now(timezone.utc)


async def set_concept_status(job_id: str, concept_id: str, status_text: str) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            row = await session.get(
                MaterialJobConcept,
                {"job_id": job_id, "concept_id": concept_id},
            )
            if not row:
                return
            row.status = status_text
            row.updated_at = datetime.now(timezone.utc)


async def get_concept(concept_id: str) -> Concept | None:
    async with AsyncSessionFactory() as session:
        return await session.get(Concept, concept_id)
