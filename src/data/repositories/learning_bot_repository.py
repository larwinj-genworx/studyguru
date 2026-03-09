from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select

from src.data.clients.postgres import AsyncSessionFactory
from src.data.models.postgres.models import LearningBotMessage, LearningBotSession
from src.schemas.learning_bot import LearningBotMessageRole, LearningBotSessionStatus


async def get_active_session(user_id: str, concept_id: str) -> LearningBotSession | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(LearningBotSession)
            .where(
                LearningBotSession.user_id == user_id,
                LearningBotSession.concept_id == concept_id,
                LearningBotSession.status == LearningBotSessionStatus.active,
            )
            .order_by(desc(LearningBotSession.updated_at))
        )
        return result.scalars().first()


async def create_session(session_model: LearningBotSession) -> LearningBotSession:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add(session_model)
        return session_model


async def list_sessions_for_subject(
    subject_id: str,
    user_ids: list[str] | None = None,
) -> list[LearningBotSession]:
    async with AsyncSessionFactory() as session:
        stmt = select(LearningBotSession).where(LearningBotSession.subject_id == subject_id)
        if user_ids is not None:
            if not user_ids:
                return []
            stmt = stmt.where(LearningBotSession.user_id.in_(user_ids))
        stmt = stmt.order_by(desc(LearningBotSession.last_message_at), desc(LearningBotSession.updated_at))
        result = await session.execute(stmt)
        return result.scalars().all()


async def update_session(session_model: LearningBotSession) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            db_session = await session.get(LearningBotSession, session_model.id)
            if not db_session:
                return
            db_session.status = session_model.status
            db_session.title = session_model.title
            db_session.session_meta = session_model.session_meta
            db_session.last_message_at = session_model.last_message_at
            db_session.updated_at = session_model.updated_at


async def archive_active_sessions(user_id: str, concept_id: str) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            result = await session.execute(
                select(LearningBotSession).where(
                    LearningBotSession.user_id == user_id,
                    LearningBotSession.concept_id == concept_id,
                    LearningBotSession.status == LearningBotSessionStatus.active,
                )
            )
            now = datetime.now(timezone.utc)
            for row in result.scalars().all():
                row.status = LearningBotSessionStatus.archived
                row.updated_at = now


async def list_messages(session_id: str, limit: int | None = None) -> list[LearningBotMessage]:
    async with AsyncSessionFactory() as session:
        if limit is not None and limit > 0:
            stmt = (
                select(LearningBotMessage)
                .where(LearningBotMessage.session_id == session_id)
                .order_by(desc(LearningBotMessage.created_at))
                .limit(limit)
            )
        else:
            stmt = (
                select(LearningBotMessage)
                .where(LearningBotMessage.session_id == session_id)
                .order_by(LearningBotMessage.created_at)
            )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        if limit is not None and limit > 0:
            rows.reverse()
        return rows


async def create_message(message: LearningBotMessage) -> LearningBotMessage:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add(message)
        return message


async def count_messages_by_session_ids(
    session_ids: list[str],
    role: LearningBotMessageRole | None = None,
) -> dict[str, int]:
    if not session_ids:
        return {}
    async with AsyncSessionFactory() as session:
        stmt = select(LearningBotMessage).where(LearningBotMessage.session_id.in_(session_ids))
        if role is not None:
            stmt = stmt.where(LearningBotMessage.role == role)
        result = await session.execute(stmt)
        counts: dict[str, int] = {}
        for row in result.scalars().all():
            counts[row.session_id] = counts.get(row.session_id, 0) + 1
        return counts
