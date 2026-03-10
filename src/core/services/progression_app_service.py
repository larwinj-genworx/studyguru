from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status

from src.core.services import progression_service
from src.data.models.postgres.models import StudentConceptProgress, Subject
from src.data.repositories import study_material_repository
from src.schemas.study_material import (
    MaterialLifecycleStatus,
    StudentSubjectProgressResponse,
    StudentTopicProgressResponse,
    StudentTopicProgressState,
)


async def get_student_subject_progress(
    subject_id: str,
    user_id: str,
) -> StudentSubjectProgressResponse:
    subject = await _get_published_subject(subject_id)
    concepts = await _list_trackable_concepts(subject.id)
    progress_map = await _load_progress_map(user_id=user_id, subject_id=subject.id)
    return progression_service.build_student_subject_progress(
        subject=subject,
        concepts=concepts,
        progress_map=progress_map,
    )


async def ensure_student_can_access_concept(
    subject_id: str,
    concept_id: str,
    user_id: str,
) -> StudentTopicProgressResponse:
    subject_progress = await get_student_subject_progress(subject_id, user_id)
    for topic in subject_progress.topics:
        if topic.concept_id != concept_id:
            continue
        if topic.is_locked:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=topic.blocker_message or "Complete the current topic before opening this one.",
            )
        return topic
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")


async def mark_topic_learning_complete(
    subject_id: str,
    concept_id: str,
    user_id: str,
) -> StudentTopicProgressResponse:
    topic = await ensure_student_can_access_concept(subject_id, concept_id, user_id)
    if topic.state == StudentTopicProgressState.passed:
        return topic

    existing = await study_material_repository.get_student_concept_progress(user_id, concept_id)
    now = datetime.now(timezone.utc)
    progress = existing or StudentConceptProgress(
        student_id=user_id,
        subject_id=subject_id,
        concept_id=concept_id,
        created_at=now,
    )
    if progress.learning_completed_at is None:
        progress.learning_completed_at = now
    progress.updated_at = now
    await study_material_repository.upsert_student_concept_progress(progress)
    refreshed = await get_student_subject_progress(subject_id, user_id)
    return _find_topic_or_404(refreshed, concept_id)


async def ensure_topic_assessment_ready(
    subject_id: str,
    concept_id: str,
    user_id: str,
) -> StudentTopicProgressResponse:
    topic = await ensure_student_can_access_concept(subject_id, concept_id, user_id)
    if topic.state == StudentTopicProgressState.passed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This topic is already passed. You can move to the next topic or review it again.",
        )
    if topic.learning_completed_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the current topic before starting its assessment.",
        )
    return topic


async def record_topic_assessment_outcome(
    *,
    subject_id: str,
    concept_id: str,
    user_id: str,
    session_id: str,
    score_percent: float,
    passed: bool,
) -> StudentTopicProgressResponse:
    existing = await study_material_repository.get_student_concept_progress(user_id, concept_id)
    now = datetime.now(timezone.utc)
    progress = existing or StudentConceptProgress(
        student_id=user_id,
        subject_id=subject_id,
        concept_id=concept_id,
        created_at=now,
    )
    if progress.learning_completed_at is None:
        progress.learning_completed_at = now
    progress.assessment_attempts = int(progress.assessment_attempts or 0) + 1
    progress.latest_score_percent = round(score_percent, 2)
    progress.best_score_percent = (
        round(max(progress.best_score_percent or 0.0, score_percent), 2)
        if progress.best_score_percent is not None
        else round(score_percent, 2)
    )
    progress.last_assessment_session_id = session_id
    progress.passed_at = now if passed else None
    progress.updated_at = now
    await study_material_repository.upsert_student_concept_progress(progress)
    refreshed = await get_student_subject_progress(subject_id, user_id)
    return _find_topic_or_404(refreshed, concept_id)


def _find_topic_or_404(
    subject_progress: StudentSubjectProgressResponse,
    concept_id: str,
) -> StudentTopicProgressResponse:
    for topic in subject_progress.topics:
        if topic.concept_id == concept_id:
            return topic
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")


async def _get_published_subject(subject_id: str) -> Subject:
    subject = await study_material_repository.get_subject(subject_id)
    if not subject or not subject.published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject is not available for students.",
        )
    return subject


async def _list_trackable_concepts(subject_id: str):
    concepts = await study_material_repository.list_concepts(subject_id)
    published = [
        concept
        for concept in concepts
        if concept.material_status == MaterialLifecycleStatus.published
    ]
    return published if published else concepts


async def _load_progress_map(
    *,
    user_id: str,
    subject_id: str,
) -> dict[str, StudentConceptProgress]:
    rows = await study_material_repository.list_student_concept_progress(user_id, subject_id)
    return {row.concept_id: row for row in rows}
