from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, select

from src.data.clients.postgres import AsyncSessionFactory
from src.data.models.postgres.models import QuizQuestion, QuizResponse, QuizSession


async def list_questions_for_concept(
    concept_id: str,
    material_version: int,
) -> list[QuizQuestion]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(QuizQuestion).where(
                QuizQuestion.concept_id == concept_id,
                QuizQuestion.material_version == material_version,
            )
        )
        return result.scalars().all()


async def get_question(question_id: str) -> QuizQuestion | None:
    async with AsyncSessionFactory() as session:
        return await session.get(QuizQuestion, question_id)


async def list_questions_by_ids(question_ids: list[str]) -> list[QuizQuestion]:
    if not question_ids:
        return []
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(QuizQuestion).where(QuizQuestion.id.in_(question_ids))
        )
        return result.scalars().all()


async def create_questions(questions: list[QuizQuestion]) -> list[QuizQuestion]:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add_all(questions)
            await session.flush()
        return questions


async def create_session(session_model: QuizSession) -> QuizSession:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            session.add(session_model)
        return session_model


async def list_sessions_for_subject(
    subject_id: str,
    user_ids: list[str] | None = None,
) -> list[QuizSession]:
    async with AsyncSessionFactory() as session:
        stmt = select(QuizSession).where(QuizSession.subject_id == subject_id)
        if user_ids is not None:
            if not user_ids:
                return []
            stmt = stmt.where(QuizSession.user_id.in_(user_ids))
        stmt = stmt.order_by(desc(QuizSession.updated_at), desc(QuizSession.started_at))
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_session(session_id: str) -> QuizSession | None:
    async with AsyncSessionFactory() as session:
        return await session.get(QuizSession, session_id)


async def update_session(session_model: QuizSession) -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            db_session = await session.get(QuizSession, session_model.id)
            if not db_session:
                return
            db_session.status = session_model.status
            db_session.current_index = session_model.current_index
            db_session.total_questions = session_model.total_questions
            db_session.correct_count = session_model.correct_count
            db_session.incorrect_count = session_model.incorrect_count
            db_session.score_percent = session_model.score_percent
            db_session.question_ids = session_model.question_ids
            db_session.concept_ids = session_model.concept_ids
            db_session.session_meta = session_model.session_meta
            db_session.report = session_model.report
            db_session.completed_at = session_model.completed_at
            db_session.updated_at = datetime.now(timezone.utc)


async def get_response(session_id: str, question_id: str) -> QuizResponse | None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(QuizResponse).where(
                QuizResponse.session_id == session_id,
                QuizResponse.question_id == question_id,
            )
        )
        return result.scalar_one_or_none()


async def upsert_response(response: QuizResponse) -> QuizResponse:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            result = await session.execute(
                select(QuizResponse).where(
                    QuizResponse.session_id == response.session_id,
                    QuizResponse.question_id == response.question_id,
                )
            )
            existing = result.scalar_one_or_none()
            if not existing:
                session.add(response)
                return response
            existing.selected_option = response.selected_option
            existing.is_correct = response.is_correct
            existing.attempts = response.attempts
            existing.hints_used = response.hints_used
            existing.attempt_log = response.attempt_log
            existing.answered_at = response.answered_at
            existing.updated_at = datetime.now(timezone.utc)
            return existing


async def list_responses_by_session(session_id: str) -> list[QuizResponse]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(QuizResponse).where(QuizResponse.session_id == session_id)
        )
        return result.scalars().all()
