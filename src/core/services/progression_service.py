from __future__ import annotations

from src.data.models.postgres.models import Concept, StudentConceptProgress, Subject
from src.schemas.study_material import (
    StudentSubjectProgressResponse,
    StudentTopicProgressResponse,
    StudentTopicProgressState,
)


def build_student_subject_progress(
    *,
    subject: Subject,
    concepts: list[Concept],
    progress_map: dict[str, StudentConceptProgress],
) -> StudentSubjectProgressResponse:
    topics: list[StudentTopicProgressResponse] = []
    current_topic: StudentTopicProgressResponse | None = None
    completed_topics = 0

    for concept in concepts:
        progress = progress_map.get(concept.id)
        if progress and progress.passed_at:
            completed_topics += 1
            topic = StudentTopicProgressResponse(
                concept_id=concept.id,
                name=concept.name,
                description=concept.description,
                topic_order=concept.topic_order,
                pass_percentage=concept.pass_percentage,
                material_status=concept.material_status,
                material_version=concept.material_version,
                state=StudentTopicProgressState.passed,
                learning_completed_at=progress.learning_completed_at,
                passed_at=progress.passed_at,
                latest_score_percent=progress.latest_score_percent,
                best_score_percent=progress.best_score_percent,
                assessment_attempts=progress.assessment_attempts,
            )
            topics.append(topic)
            continue

        if current_topic is None:
            state = StudentTopicProgressState.available
            if progress and progress.learning_completed_at is not None:
                if (
                    progress.assessment_attempts > 0
                    and progress.latest_score_percent is not None
                    and progress.latest_score_percent < concept.pass_percentage
                ):
                    state = StudentTopicProgressState.retry_required
                else:
                    state = StudentTopicProgressState.ready_for_assessment
            topic = StudentTopicProgressResponse(
                concept_id=concept.id,
                name=concept.name,
                description=concept.description,
                topic_order=concept.topic_order,
                pass_percentage=concept.pass_percentage,
                material_status=concept.material_status,
                material_version=concept.material_version,
                state=state,
                is_current=True,
                learning_completed_at=progress.learning_completed_at if progress else None,
                passed_at=progress.passed_at if progress else None,
                latest_score_percent=progress.latest_score_percent if progress else None,
                best_score_percent=progress.best_score_percent if progress else None,
                assessment_attempts=progress.assessment_attempts if progress else 0,
            )
            topics.append(topic)
            current_topic = topic
            continue

        blocker_message = (
            f"Complete Topic {current_topic.topic_order}: {current_topic.name} "
            f"and pass {current_topic.pass_percentage}% to unlock this topic."
        )
        topics.append(
            StudentTopicProgressResponse(
                concept_id=concept.id,
                name=concept.name,
                description=concept.description,
                topic_order=concept.topic_order,
                pass_percentage=concept.pass_percentage,
                material_status=concept.material_status,
                material_version=concept.material_version,
                state=StudentTopicProgressState.locked,
                is_locked=True,
                learning_completed_at=progress.learning_completed_at if progress else None,
                passed_at=progress.passed_at if progress else None,
                latest_score_percent=progress.latest_score_percent if progress else None,
                best_score_percent=progress.best_score_percent if progress else None,
                assessment_attempts=progress.assessment_attempts if progress else 0,
                blocker_message=blocker_message,
            )
        )

    total_topics = len(concepts)
    return StudentSubjectProgressResponse(
        subject_id=subject.id,
        subject_name=subject.name,
        grade_level=subject.grade_level,
        total_topics=total_topics,
        completed_topics=completed_topics,
        progress_percent=round((completed_topics / total_topics) * 100, 1) if total_topics else 0.0,
        current_concept_id=current_topic.concept_id if current_topic else None,
        current_concept_name=current_topic.name if current_topic else None,
        topics=topics,
    )
