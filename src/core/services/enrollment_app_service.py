from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import HTTPException, status

from src.core.services import progression_service, study_material_service
from src.data.models.postgres.models import (
    Concept,
    ConceptBookmark,
    LearningBotSession,
    QuizSession,
    StudentConceptProgress,
    Subject,
    SubjectEnrollment,
)
from src.data.repositories import auth_repository, learning_bot_repository, quiz_repository, study_material_repository
from src.schemas.learning_bot import LearningBotMessageRole
from src.schemas.quiz import QuizSessionStatus, QuizSessionType, QuizTopicPerformance
from src.schemas.study_material import (
    AdminEnrolledStudentResponse,
    AdminStudentActivityResponse,
    AdminStudentConceptActivityResponse,
    AdminStudentLearningSessionResponse,
    AdminStudentQuizReportResponse,
    ConceptBookmarkResponse,
    MaterialLifecycleStatus,
    StudentActivityEventResponse,
    StudentActivityOverviewResponse,
    StudentSubjectProgressResponse,
    StudentTopicProgressResponse,
    StudentTopicProgressState,
    SubjectResponse,
)

_TRACKABLE_STATUSES = {
    MaterialLifecycleStatus.approved,
    MaterialLifecycleStatus.published,
}


async def sync_organization_subject_access(
    organization_id: str,
    *,
    student_ids: list[str] | None = None,
    subject_ids: list[str] | None = None,
) -> None:
    target_student_ids = student_ids or [
        user.id
        for user in await auth_repository.list_users_for_organization(organization_id, role="student")
    ]
    target_subject_ids = subject_ids or [
        subject.id
        for subject in await study_material_repository.list_subjects_for_organization(organization_id)
    ]
    if not target_student_ids or not target_subject_ids:
        return
    await study_material_repository.ensure_subject_enrollments(
        student_ids=target_student_ids,
        subject_ids=target_subject_ids,
    )


async def list_student_subjects(user_id: str) -> list[SubjectResponse]:
    user = await auth_repository.get_user_by_id(user_id)
    if not user or user.role.lower() != "student":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    subjects = await study_material_repository.list_subjects_for_organization(user.organization_id)
    enrollments = await study_material_repository.list_enrollments_for_student(user_id)
    enrollment_map = {item.subject_id: item for item in enrollments}

    return [
        study_material_service.to_subject_response(
            subject,
            [],
            enrollment=enrollment_map.get(subject.id),
        )
        for subject in subjects
    ]


async def ensure_student_enrollment(
    subject_id: str,
    user_id: str,
) -> tuple[Subject, SubjectEnrollment]:
    user = await auth_repository.get_user_by_id(user_id)
    if not user or user.role.lower() != "student":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    subject = await study_material_repository.get_subject(subject_id)
    if not subject or not subject.published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject is not available for students.",
        )
    if subject.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This subject is not available for your organization.",
        )
    enrollment = await study_material_repository.get_subject_enrollment(user_id, subject_id)
    if not enrollment:
        enrollment = await study_material_repository.create_subject_enrollment(user_id, subject_id)
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This syllabus is not available for your account.",
            )
    return subject, enrollment


async def list_admin_subject_enrollments(
    subject_id: str,
    owner_id: str,
) -> list[AdminEnrolledStudentResponse]:
    subject = await _get_admin_subject(subject_id, owner_id)
    concepts = await study_material_repository.list_concepts(subject.id)
    trackable_concepts = _get_trackable_concepts(concepts)
    enrollments = await study_material_repository.list_subject_enrollments(subject.id)
    if not enrollments:
        return []

    student_ids = [enrollment.student_id for enrollment in enrollments]
    users = await auth_repository.list_users_by_ids(student_ids)
    user_map = {user.id: user for user in users if user.role.lower() == "student"}

    bookmarks = await study_material_repository.list_bookmarks_for_users(student_ids, subject_id=subject.id)
    progress_rows = await study_material_repository.list_student_concept_progress_for_users(
        student_ids=student_ids,
        subject_id=subject.id,
    )
    quiz_sessions = await quiz_repository.list_sessions_for_subject(subject.id, user_ids=student_ids)
    learning_sessions = await learning_bot_repository.list_sessions_for_subject(subject.id, user_ids=student_ids)
    learning_message_counts = await learning_bot_repository.count_messages_by_session_ids(
        [session.id for session in learning_sessions]
    )

    bookmark_map = _group_by_user(bookmarks)
    progress_map = _group_progress_by_user(progress_rows)
    quiz_map = _group_by_user(quiz_sessions)
    learning_map = _group_by_user(learning_sessions)
    trackable_concept_ids = {concept.id for concept in trackable_concepts}

    responses: list[AdminEnrolledStudentResponse] = []
    for enrollment in enrollments:
        user = user_map.get(enrollment.student_id)
        if not user:
            continue
        subject_progress = progression_service.build_student_subject_progress(
            subject=subject,
            concepts=trackable_concepts,
            progress_map=progress_map.get(enrollment.student_id, {}),
        )
        overview = _build_overview(
            enrollment=enrollment,
            trackable_concept_ids=trackable_concept_ids,
            bookmarks=bookmark_map.get(enrollment.student_id, []),
            quiz_sessions=quiz_map.get(enrollment.student_id, []),
            learning_sessions=learning_map.get(enrollment.student_id, []),
            learning_message_counts=learning_message_counts,
            subject_progress=subject_progress,
        )
        responses.append(
            AdminEnrolledStudentResponse(
                student_id=user.id,
                student_email=user.email,
                enrolled_at=enrollment.enrolled_at,
                overview=overview,
            )
        )
    return responses


async def get_admin_student_activity(
    subject_id: str,
    student_id: str,
    owner_id: str,
) -> AdminStudentActivityResponse:
    subject = await _get_admin_subject(subject_id, owner_id)
    user = await auth_repository.get_user_by_id(student_id)
    if not user or user.role.lower() != "student":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found.")

    enrollment = await study_material_repository.get_subject_enrollment(student_id, subject.id)
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student is not assigned to this syllabus.",
        )

    concepts = await study_material_repository.list_concepts(subject.id)
    trackable_concepts = _get_trackable_concepts(concepts)
    trackable_concept_ids = {concept.id for concept in trackable_concepts}
    concept_name_map = {concept.id: concept.name for concept in concepts}

    bookmarks = await study_material_repository.list_bookmarks(student_id, subject_id=subject.id)
    progress_rows = await study_material_repository.list_student_concept_progress(student_id, subject.id)
    quiz_sessions = await quiz_repository.list_sessions_for_subject(subject.id, user_ids=[student_id])
    learning_sessions = await learning_bot_repository.list_sessions_for_subject(subject.id, user_ids=[student_id])
    learning_message_counts = await learning_bot_repository.count_messages_by_session_ids(
        [session.id for session in learning_sessions]
    )
    learning_prompt_counts = await learning_bot_repository.count_messages_by_session_ids(
        [session.id for session in learning_sessions],
        role=LearningBotMessageRole.user,
    )
    subject_progress = progression_service.build_student_subject_progress(
        subject=subject,
        concepts=trackable_concepts,
        progress_map={row.concept_id: row for row in progress_rows},
    )

    overview = _build_overview(
        enrollment=enrollment,
        trackable_concept_ids=trackable_concept_ids,
        bookmarks=bookmarks,
        quiz_sessions=quiz_sessions,
        learning_sessions=learning_sessions,
        learning_message_counts=learning_message_counts,
        subject_progress=subject_progress,
    )

    return AdminStudentActivityResponse(
        subject_id=subject.id,
        subject_name=subject.name,
        grade_level=subject.grade_level,
        student_id=user.id,
        student_email=user.email,
        enrolled_at=enrollment.enrolled_at,
        overview=overview,
        concept_activity=_build_concept_activity(
            concepts=trackable_concepts,
            subject_progress=subject_progress,
            bookmarks=bookmarks,
            quiz_sessions=quiz_sessions,
            learning_sessions=learning_sessions,
            learning_message_counts=learning_message_counts,
        ),
        bookmarks=[
            ConceptBookmarkResponse(
                concept_id=bookmark.concept_id,
                concept_name=concept_name_map.get(bookmark.concept_id, "Concept"),
                subject_id=subject.id,
                subject_name=subject.name,
                created_at=bookmark.created_at,
            )
            for bookmark in sorted(bookmarks, key=lambda item: item.created_at, reverse=True)
        ],
        learning_sessions=_build_learning_sessions(
            learning_sessions=learning_sessions,
            concept_name_map=concept_name_map,
            learning_message_counts=learning_message_counts,
            learning_prompt_counts=learning_prompt_counts,
        ),
        quiz_reports=_build_quiz_reports(quiz_sessions=quiz_sessions),
        recent_activity=_build_recent_activity(
            enrollment=enrollment,
            bookmarks=bookmarks,
            quiz_sessions=quiz_sessions,
            learning_sessions=learning_sessions,
            concept_name_map=concept_name_map,
            learning_prompt_counts=learning_prompt_counts,
        ),
    )


async def _get_admin_subject(subject_id: str, owner_id: str) -> Subject:
    subject = await study_material_repository.get_subject_for_owner(subject_id, owner_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    return subject


def _group_by_user(items: list[ConceptBookmark] | list[QuizSession] | list[LearningBotSession]) -> dict[str, list]:
    grouped: dict[str, list] = defaultdict(list)
    for item in items:
        grouped[item.user_id].append(item)
    return grouped


def _group_progress_by_user(
    items: list[StudentConceptProgress],
) -> dict[str, dict[str, StudentConceptProgress]]:
    grouped: dict[str, dict[str, StudentConceptProgress]] = defaultdict(dict)
    for item in items:
        grouped[item.student_id][item.concept_id] = item
    return grouped


def _get_trackable_concepts(concepts: list[Concept]) -> list[Concept]:
    tracked = [concept for concept in concepts if concept.material_status in _TRACKABLE_STATUSES]
    return tracked if tracked else concepts


def _build_overview(
    *,
    enrollment: SubjectEnrollment,
    trackable_concept_ids: set[str],
    bookmarks: list[ConceptBookmark],
    quiz_sessions: list[QuizSession],
    learning_sessions: list[LearningBotSession],
    learning_message_counts: dict[str, int],
    subject_progress: StudentSubjectProgressResponse,
) -> StudentActivityOverviewResponse:
    bookmark_concept_ids = {
        bookmark.concept_id for bookmark in bookmarks if bookmark.concept_id in trackable_concept_ids
    }
    quiz_concept_ids = _collect_quiz_concept_ids(quiz_sessions, trackable_concept_ids)
    learning_concept_ids = {
        session.concept_id for session in learning_sessions if session.concept_id in trackable_concept_ids
    }
    engaged_concept_ids = bookmark_concept_ids | quiz_concept_ids | learning_concept_ids

    completed_sessions = [
        session for session in quiz_sessions if session.status == QuizSessionStatus.completed
    ]
    accuracies = [
        accuracy
        for accuracy in (_extract_session_accuracy(session) for session in completed_sessions)
        if accuracy is not None
    ]

    last_activity_candidates = [enrollment.enrolled_at]
    last_activity_candidates.extend(bookmark.created_at for bookmark in bookmarks)
    last_activity_candidates.extend(_resolve_quiz_activity_at(session) for session in quiz_sessions)
    last_activity_candidates.extend(session.last_message_at for session in learning_sessions)

    current_topic = next((topic for topic in subject_progress.topics if topic.is_current), None)
    failed_assessments = sum(
        1 for topic in subject_progress.topics if topic.state == StudentTopicProgressState.retry_required
    )
    passed_assessments = sum(
        1 for topic in subject_progress.topics if topic.state == StudentTopicProgressState.passed
    )
    total_concepts = subject_progress.total_topics or len(trackable_concept_ids)
    engaged_concepts = len(engaged_concept_ids)

    return StudentActivityOverviewResponse(
        total_concepts=total_concepts,
        engaged_concepts=engaged_concepts,
        completed_topics=subject_progress.completed_topics,
        progress_percent=subject_progress.progress_percent,
        current_topic_name=current_topic.name if current_topic else None,
        current_topic_order=current_topic.topic_order if current_topic else None,
        failed_assessments=failed_assessments,
        passed_assessments=passed_assessments,
        bookmarks_count=len(bookmarks),
        total_quiz_sessions=len(quiz_sessions),
        completed_quizzes=len(completed_sessions),
        average_quiz_accuracy=round(sum(accuracies) / len(accuracies), 4) if accuracies else None,
        best_quiz_accuracy=max(accuracies) if accuracies else None,
        learning_sessions=len(learning_sessions),
        learning_messages=sum(learning_message_counts.get(session.id, 0) for session in learning_sessions),
        last_activity_at=max(last_activity_candidates) if last_activity_candidates else None,
    )


def _collect_quiz_concept_ids(
    quiz_sessions: list[QuizSession],
    allowed_concept_ids: set[str],
) -> set[str]:
    concept_ids: set[str] = set()
    for session in quiz_sessions:
        for concept_id in session.concept_ids or []:
            if concept_id in allowed_concept_ids:
                concept_ids.add(concept_id)
    return concept_ids


def _build_concept_activity(
    *,
    concepts: list[Concept],
    subject_progress: StudentSubjectProgressResponse,
    bookmarks: list[ConceptBookmark],
    quiz_sessions: list[QuizSession],
    learning_sessions: list[LearningBotSession],
    learning_message_counts: dict[str, int],
) -> list[AdminStudentConceptActivityResponse]:
    bookmark_map = {bookmark.concept_id: bookmark for bookmark in bookmarks}
    progress_topic_map = {topic.concept_id: topic for topic in subject_progress.topics}
    quiz_session_map: dict[str, list[QuizSession]] = defaultdict(list)
    quiz_accuracy_map: dict[str, list[float]] = defaultdict(list)
    learning_session_map: dict[str, list[LearningBotSession]] = defaultdict(list)

    for session in quiz_sessions:
        concept_ids = list(dict.fromkeys(session.concept_ids or []))
        for concept_id in concept_ids:
            quiz_session_map[concept_id].append(session)
        topic_accuracy_map = _extract_topic_accuracies(session)
        for concept_id, accuracy in topic_accuracy_map.items():
            quiz_accuracy_map[concept_id].append(accuracy)

    for session in learning_sessions:
        learning_session_map[session.concept_id].append(session)

    responses: list[AdminStudentConceptActivityResponse] = []
    for concept in concepts:
        progress_topic = progress_topic_map.get(concept.id)
        concept_quizzes = quiz_session_map.get(concept.id, [])
        completed_quizzes = [
            session for session in concept_quizzes if session.status == QuizSessionStatus.completed
        ]
        concept_learning_sessions = learning_session_map.get(concept.id, [])
        message_count = sum(
            learning_message_counts.get(session.id, 0) for session in concept_learning_sessions
        )
        accuracy_values = quiz_accuracy_map.get(concept.id, [])
        last_activity_candidates = []
        if concept.id in bookmark_map:
            last_activity_candidates.append(bookmark_map[concept.id].created_at)
        last_activity_candidates.extend(_resolve_quiz_activity_at(session) for session in concept_quizzes)
        last_activity_candidates.extend(session.last_message_at for session in concept_learning_sessions)

        responses.append(
            AdminStudentConceptActivityResponse(
                concept_id=concept.id,
                concept_name=concept.name,
                topic_order=concept.topic_order,
                pass_percentage=concept.pass_percentage,
                status=_resolve_concept_status(
                    has_bookmark=concept.id in bookmark_map,
                    completed_quizzes=len(completed_quizzes),
                    best_accuracy=max(accuracy_values) if accuracy_values else None,
                    learning_sessions=len(concept_learning_sessions),
                    progress_state=progress_topic.state if progress_topic else None,
                ),
                progress_state=progress_topic.state if progress_topic else None,
                is_current=progress_topic.is_current if progress_topic else False,
                has_bookmark=concept.id in bookmark_map,
                learning_completed_at=progress_topic.learning_completed_at if progress_topic else None,
                assessment_attempts=progress_topic.assessment_attempts if progress_topic else 0,
                latest_score_percent=progress_topic.latest_score_percent if progress_topic else None,
                best_score_percent=progress_topic.best_score_percent if progress_topic else None,
                passed_at=progress_topic.passed_at if progress_topic else None,
                blocker_message=progress_topic.blocker_message if progress_topic else None,
                quiz_sessions=len(concept_quizzes),
                completed_quizzes=len(completed_quizzes),
                best_quiz_accuracy=max(accuracy_values) if accuracy_values else None,
                learning_sessions=len(concept_learning_sessions),
                learning_messages=message_count,
                last_activity_at=max(last_activity_candidates) if last_activity_candidates else None,
            )
        )
    return responses


def _resolve_concept_status(
    *,
    has_bookmark: bool,
    completed_quizzes: int,
    best_accuracy: float | None,
    learning_sessions: int,
    progress_state: StudentTopicProgressState | None,
) -> str:
    if progress_state == StudentTopicProgressState.passed:
        return "strong"
    if progress_state == StudentTopicProgressState.retry_required:
        return "needs_support"
    engaged = has_bookmark or completed_quizzes > 0 or learning_sessions > 0
    if not engaged:
        return "not_started"
    if best_accuracy is not None and best_accuracy >= 0.8:
        return "strong"
    if best_accuracy is not None and best_accuracy < 0.5:
        return "needs_support"
    return "active"


def _build_learning_sessions(
    *,
    learning_sessions: list[LearningBotSession],
    concept_name_map: dict[str, str],
    learning_message_counts: dict[str, int],
    learning_prompt_counts: dict[str, int],
) -> list[AdminStudentLearningSessionResponse]:
    sessions = sorted(
        learning_sessions,
        key=lambda session: session.last_message_at,
        reverse=True,
    )
    return [
        AdminStudentLearningSessionResponse(
            session_id=session.id,
            concept_id=session.concept_id,
            concept_name=concept_name_map.get(session.concept_id, "Concept"),
            status=session.status,
            title=session.title,
            prompt_count=learning_prompt_counts.get(session.id, 0),
            message_count=learning_message_counts.get(session.id, 0),
            last_message_at=session.last_message_at,
        )
        for session in sessions
    ]


def _build_quiz_reports(
    *,
    quiz_sessions: list[QuizSession],
) -> list[AdminStudentQuizReportResponse]:
    sessions = sorted(quiz_sessions, key=_resolve_quiz_activity_at, reverse=True)
    reports: list[AdminStudentQuizReportResponse] = []
    for session in sessions:
        report_payload = session.report if isinstance(session.report, dict) else {}
        topic_breakdown = []
        for item in report_payload.get("topic_breakdown", []):
            try:
                topic_breakdown.append(QuizTopicPerformance(**item))
            except Exception:
                continue
        recommendations = [
            str(item).strip() for item in report_payload.get("recommendations", []) if str(item).strip()
        ]
        first_attempt_correct_count = report_payload.get("correct_count")
        if not isinstance(first_attempt_correct_count, int):
            first_attempt_correct_count = (
                _first_attempt_count_from_meta(report_payload)
                or _first_attempt_count_from_session(session)
                or 0
            )
        reports.append(
            AdminStudentQuizReportResponse(
                session_id=session.id,
                session_type=session.session_type or QuizSessionType.custom_practice,
                status=session.status,
                started_at=session.started_at,
                completed_at=session.completed_at,
                accuracy=_extract_session_accuracy(session),
                score_percent=session.score_percent,
                correct_count=first_attempt_correct_count,
                total_questions=session.total_questions,
                required_pass_percentage=session.required_pass_percentage,
                passed=session.passed,
                topics=topic_breakdown,
                recommendations=recommendations,
            )
        )
    return reports


def _build_recent_activity(
    *,
    enrollment: SubjectEnrollment,
    bookmarks: list[ConceptBookmark],
    quiz_sessions: list[QuizSession],
    learning_sessions: list[LearningBotSession],
    concept_name_map: dict[str, str],
    learning_prompt_counts: dict[str, int],
) -> list[StudentActivityEventResponse]:
    events: list[StudentActivityEventResponse] = [
        StudentActivityEventResponse(
            event_type="enrollment",
            title="Assigned to syllabus",
            occurred_at=enrollment.enrolled_at,
        )
    ]

    for bookmark in bookmarks:
        events.append(
            StudentActivityEventResponse(
                event_type="bookmark",
                title="Bookmarked topic",
                description=concept_name_map.get(bookmark.concept_id, "Concept"),
                occurred_at=bookmark.created_at,
                concept_id=bookmark.concept_id,
                concept_name=concept_name_map.get(bookmark.concept_id),
            )
        )

    for session in quiz_sessions:
        concept_names = [
            concept_name_map.get(concept_id, "Concept")
            for concept_id in (session.concept_ids or [])
            if concept_id in concept_name_map
        ]
        accuracy = _extract_session_accuracy(session)
        score_percent = (
            round(float(session.score_percent), 1) if session.score_percent is not None else None
        )
        if session.status == QuizSessionStatus.completed:
            description = None
            title = "Completed a practice quiz"
            event_type = "quiz_completed"
            if session.session_type == QuizSessionType.topic_assessment:
                title = "Passed topic assessment" if session.passed else "Completed topic assessment"
                event_type = "topic_assessment_passed" if session.passed else "topic_assessment_completed"
                if session.passed is False:
                    title = "Retry needed after assessment"
                    event_type = "topic_assessment_retry_required"
            if score_percent is not None:
                description = f"{score_percent}% score"
            elif accuracy is not None:
                description = f"{round(accuracy * 100)}% accuracy"
            if description and session.required_pass_percentage is not None:
                description = (
                    f"{description} against {session.required_pass_percentage}% requirement"
                )
            if description and concept_names:
                description = f"{description} for {', '.join(concept_names[:3])}"
            events.append(
                StudentActivityEventResponse(
                    event_type=event_type,
                    title=title,
                    description=description,
                    occurred_at=session.completed_at or _resolve_quiz_activity_at(session),
                    concept_name=concept_names[0] if len(concept_names) == 1 else None,
                )
            )
        else:
            title = (
                "Started topic assessment"
                if session.session_type == QuizSessionType.topic_assessment
                else "Started a practice quiz"
            )
            events.append(
                StudentActivityEventResponse(
                    event_type="quiz_started",
                    title=title,
                    description=", ".join(concept_names[:3]) if concept_names else None,
                    occurred_at=session.started_at,
                    concept_name=concept_names[0] if len(concept_names) == 1 else None,
                )
            )

    for session in learning_sessions:
        prompt_count = learning_prompt_counts.get(session.id, 0)
        description = (
            f"{prompt_count} prompt(s) asked"
            if prompt_count
            else "Opened a guided learning conversation"
        )
        events.append(
            StudentActivityEventResponse(
                event_type="learning_bot",
                title="Used the learning assistant",
                description=description,
                occurred_at=session.last_message_at,
                concept_id=session.concept_id,
                concept_name=concept_name_map.get(session.concept_id),
            )
        )

    return sorted(events, key=lambda event: event.occurred_at, reverse=True)[:20]


def _extract_session_accuracy(session: QuizSession) -> float | None:
    if _report_uses_first_attempt_scoring(session) and isinstance(session.report, dict):
        accuracy = session.report.get("accuracy")
        if isinstance(accuracy, (int, float)):
            return float(accuracy)
    first_attempt_correct = _first_attempt_count_from_session(session)
    if first_attempt_correct is not None and session.total_questions:
        return round(float(first_attempt_correct) / float(session.total_questions), 4)
    if session.score_percent is not None:
        return round(float(session.score_percent) / 100, 4)
    return None


def _first_attempt_count_from_meta(report_payload: dict) -> int | None:
    meta = report_payload.get("meta")
    if not isinstance(meta, dict):
        return None
    value = meta.get("first_attempt_correct_count")
    if isinstance(value, int):
        return value
    return None


def _first_attempt_count_from_session(session: QuizSession) -> int | None:
    metadata = session.session_meta if isinstance(session.session_meta, dict) else {}
    value = metadata.get("first_attempt_correct")
    if isinstance(value, int):
        return value
    return None


def _extract_topic_accuracies(session: QuizSession) -> dict[str, float]:
    accuracies: dict[str, float] = {}
    if _report_uses_first_attempt_scoring(session) and isinstance(session.report, dict):
        for item in session.report.get("topic_breakdown", []):
            concept_id = item.get("concept_id")
            accuracy = item.get("accuracy")
            if concept_id and isinstance(accuracy, (int, float)):
                accuracies[concept_id] = float(accuracy)
    if accuracies:
        return accuracies
    if len(session.concept_ids or []) == 1:
        accuracy = _extract_session_accuracy(session)
        if accuracy is not None:
            accuracies[session.concept_ids[0]] = accuracy
    return accuracies


def _report_uses_first_attempt_scoring(session: QuizSession) -> bool:
    if not isinstance(session.report, dict):
        return False
    meta = session.report.get("meta")
    if not isinstance(meta, dict):
        return False
    return meta.get("scoring_model") == "first_attempt_accuracy"


def _resolve_quiz_activity_at(session: QuizSession) -> datetime:
    return session.completed_at or session.updated_at or session.started_at
