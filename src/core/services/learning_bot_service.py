from __future__ import annotations

from src.data.models.postgres.models import Concept, LearningBotMessage, LearningBotSession, Subject
from src.schemas.learning_bot import (
    LearningBotMessageResponse,
    LearningBotSessionDetailResponse,
    LearningBotSessionResponse,
)


def to_session_response(
    *,
    session: LearningBotSession,
    subject: Subject,
    concept: Concept,
) -> LearningBotSessionResponse:
    return LearningBotSessionResponse(
        session_id=session.id,
        subject_id=subject.id,
        subject_name=subject.name,
        concept_id=concept.id,
        concept_name=concept.name,
        grade_level=subject.grade_level,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at,
    )


def to_message_response(message: LearningBotMessage) -> LearningBotMessageResponse:
    return LearningBotMessageResponse(
        message_id=message.id,
        role=message.role,
        content=message.content,
        citations=list(message.citations or []),
        follow_up_suggestions=list(message.follow_up_suggestions or []),
        meta=dict(message.message_meta or {}),
        created_at=message.created_at,
    )


def build_suggested_prompts(*, concept_name: str) -> list[str]:
    return [
        f"Explain {concept_name} in simple words",
        f"Give me one worked example on {concept_name}",
        f"Test me with 3 questions on {concept_name}",
    ]


def build_session_detail(
    *,
    session: LearningBotSession,
    subject: Subject,
    concept: Concept,
    messages: list[LearningBotMessage],
) -> LearningBotSessionDetailResponse:
    return LearningBotSessionDetailResponse(
        session=to_session_response(session=session, subject=subject, concept=concept),
        messages=[to_message_response(message) for message in messages],
        suggested_prompts=build_suggested_prompts(concept_name=concept.name),
    )
