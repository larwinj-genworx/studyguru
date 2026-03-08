from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from src.config.settings import get_settings
from src.control.learning_bot.agents import build_agent_registry
from src.control.learning_bot.services import LearningBotChatEngine
from src.core.services import learning_bot_service, learning_content_service
from src.data.models.postgres.models import LearningBotMessage, LearningBotSession
from src.data.repositories import learning_bot_repository, study_material_repository
from src.schemas.learning_bot import (
    LearningBotMessageCreate,
    LearningBotSessionDetailResponse,
    LearningBotMessageRole,
    LearningBotSessionStatus,
    LearningBotTurnResponse,
)
from src.schemas.study_material import LearningContent, MaterialLifecycleStatus


logger = logging.getLogger("uvicorn.error")

_settings = get_settings()
_chat_engine: LearningBotChatEngine | None = None


def _ensure_chat_engine() -> LearningBotChatEngine:
    global _chat_engine
    if _chat_engine is not None:
        return _chat_engine
    _chat_engine = LearningBotChatEngine(
        settings=_settings,
        agents=build_agent_registry(_settings),
    )
    return _chat_engine


async def get_student_learning_bot_session(
    *,
    subject_id: str,
    concept_id: str,
    user_id: str,
) -> LearningBotSessionDetailResponse:
    subject, concept, _material, _content = await _get_published_concept_context(
        subject_id=subject_id,
        concept_id=concept_id,
    )
    session = await _get_or_create_active_session(
        user_id=user_id,
        subject_id=subject.id,
        concept_id=concept.id,
        concept_name=concept.name,
    )
    messages = await learning_bot_repository.list_messages(session.id)
    return learning_bot_service.build_session_detail(
        session=session,
        subject=subject,
        concept=concept,
        messages=messages,
    )


async def reset_student_learning_bot_session(
    *,
    subject_id: str,
    concept_id: str,
    user_id: str,
) -> LearningBotSessionDetailResponse:
    subject, concept, _material, _content = await _get_published_concept_context(
        subject_id=subject_id,
        concept_id=concept_id,
    )
    await learning_bot_repository.archive_active_sessions(user_id=user_id, concept_id=concept.id)
    session = await _create_active_session(
        user_id=user_id,
        subject_id=subject.id,
        concept_id=concept.id,
        concept_name=concept.name,
    )
    return learning_bot_service.build_session_detail(
        session=session,
        subject=subject,
        concept=concept,
        messages=[],
    )


async def send_student_learning_bot_message(
    *,
    subject_id: str,
    concept_id: str,
    user_id: str,
    payload: LearningBotMessageCreate,
) -> LearningBotTurnResponse:
    subject, concept, material, content = await _get_published_concept_context(
        subject_id=subject_id,
        concept_id=concept_id,
    )
    session = await _get_or_create_active_session(
        user_id=user_id,
        subject_id=subject.id,
        concept_id=concept.id,
        concept_name=concept.name,
    )
    now = datetime.now(timezone.utc)
    user_message = LearningBotMessage(
        session_id=session.id,
        role=LearningBotMessageRole.user,
        content=payload.message.strip(),
        citations=[],
        follow_up_suggestions=[],
        message_meta={"message_kind": "student_prompt"},
        created_at=now,
        updated_at=now,
    )
    user_message = await learning_bot_repository.create_message(user_message)

    all_messages = await learning_bot_repository.list_messages(session.id)
    history_payload = [
        {"role": message.role.value, "content": message.content}
        for message in all_messages[-_settings.learning_bot_history_limit :]
    ]
    engine = _ensure_chat_engine()
    logger.info(
        "[LearningBot] Generating reply for user='%s' concept='%s' session='%s'",
        user_id,
        concept.name,
        session.id,
    )
    reply = await engine.generate_reply(
        subject_name=subject.name,
        grade_level=subject.grade_level,
        concept_id=concept.id,
        concept_name=concept.name,
        concept_description=concept.description,
        material_version=material.version,
        content=content,
        recent_history=history_payload,
        student_message=payload.message.strip(),
    )

    assistant_now = datetime.now(timezone.utc)
    assistant_message = LearningBotMessage(
        session_id=session.id,
        role=LearningBotMessageRole.assistant,
        content=reply.answer,
        citations=reply.citations,
        follow_up_suggestions=reply.follow_up_suggestions,
        message_meta=reply.meta,
        created_at=assistant_now,
        updated_at=assistant_now,
    )
    assistant_message = await learning_bot_repository.create_message(assistant_message)

    session.last_message_at = assistant_now
    session.updated_at = assistant_now
    session.session_meta = {
        **dict(session.session_meta or {}),
        "last_retrieval_mode": reply.meta.get("retrieval_mode"),
        "last_confidence": reply.meta.get("confidence"),
    }
    await learning_bot_repository.update_session(session)

    return LearningBotTurnResponse(
        session=learning_bot_service.to_session_response(
            session=session,
            subject=subject,
            concept=concept,
        ),
        user_message=learning_bot_service.to_message_response(user_message),
        assistant_message=learning_bot_service.to_message_response(assistant_message),
    )


async def _get_published_concept_context(
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


async def _get_or_create_active_session(
    *,
    user_id: str,
    subject_id: str,
    concept_id: str,
    concept_name: str,
) -> LearningBotSession:
    session = await learning_bot_repository.get_active_session(user_id=user_id, concept_id=concept_id)
    if session:
        return session
    return await _create_active_session(
        user_id=user_id,
        subject_id=subject_id,
        concept_id=concept_id,
        concept_name=concept_name,
    )


async def _create_active_session(
    *,
    user_id: str,
    subject_id: str,
    concept_id: str,
    concept_name: str,
) -> LearningBotSession:
    now = datetime.now(timezone.utc)
    session = LearningBotSession(
        user_id=user_id,
        subject_id=subject_id,
        concept_id=concept_id,
        status=LearningBotSessionStatus.active,
        title=f"{concept_name} tutor",
        session_meta={},
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    return await learning_bot_repository.create_session(session)
