from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from src.config.settings import get_settings
from src.control.student_quiz_generation.agents import build_agent_registry
from src.control.student_quiz_generation.services.quiz_engine import QuizEngine
from src.core.services import enrollment_app_service, quiz_service
from src.data.models.postgres.models import QuizQuestion, QuizResponse, QuizSession
from src.data.repositories import quiz_repository, study_material_repository
from src.schemas.quiz import (
    QuizAnswerRequest,
    QuizAnswerResponse,
    QuizReportResponse,
    QuizSessionResponse,
    QuizSessionStartRequest,
    QuizSessionStartResponse,
    QuizSessionStatus,
)
from src.schemas.study_material import LearningContent, MaterialLifecycleStatus


logger = logging.getLogger("uvicorn.error")

_settings = get_settings()
_quiz_engine: QuizEngine | None = None


@dataclass
class _ConceptRuntime:
    profile: quiz_service.ConceptProfile
    weight: float
    question_count: int
    questions: list[QuizQuestion]


def _ensure_quiz_engine() -> QuizEngine:
    global _quiz_engine
    if _quiz_engine is not None:
        return _quiz_engine
    _quiz_engine = QuizEngine(settings=_settings, agents=build_agent_registry(_settings))
    return _quiz_engine


async def start_student_quiz(
    payload: QuizSessionStartRequest,
    user_id: str,
) -> QuizSessionStartResponse:
    subject, _ = await enrollment_app_service.ensure_student_enrollment(
        payload.subject_id,
        user_id,
    )

    concepts = await study_material_repository.list_concepts(subject.id)
    concept_map = {concept.id: concept for concept in concepts}
    unique_ids = list(dict.fromkeys(payload.concept_ids))
    unknown = [concept_id for concept_id in unique_ids if concept_id not in concept_map]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown concept IDs: {unknown}",
        )

    latest_materials = await study_material_repository.get_latest_materials(unique_ids)
    profiles: list[quiz_service.ConceptProfile] = []
    for concept_id in unique_ids:
        concept = concept_map[concept_id]
        material = latest_materials.get(concept_id)
        if not material or material.lifecycle_status != MaterialLifecycleStatus.published:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Concept is not published yet: {concept.name}",
            )
        if not material.content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Learning content missing for concept: {concept.name}",
            )
        content = LearningContent(**material.content)
        metadata = content.metadata or {}
        complexity_score = quiz_service.compute_complexity_score(metadata)
        required_depth = quiz_service.compute_required_depth(metadata)
        profiles.append(
            quiz_service.ConceptProfile(
                concept_id=concept.id,
                concept_name=concept.name,
                complexity_score=complexity_score,
                required_depth=required_depth,
                material_version=material.version,
                content=content,
            )
        )

    if not profiles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select at least one published topic to start a quiz.",
        )

    target_count = quiz_service.compute_target_question_count(concepts=profiles, settings=_settings)
    weights = quiz_service.compute_topic_weights(profiles)
    allocation = quiz_service.allocate_question_counts(
        total_questions=target_count,
        concepts=profiles,
        weights=weights,
    )

    concept_runtime: list[_ConceptRuntime] = []
    engine = _ensure_quiz_engine()
    semaphore = asyncio.Semaphore(_settings.max_parallel_concepts)

    async def _prepare_concept(profile: quiz_service.ConceptProfile) -> _ConceptRuntime:
        async with semaphore:
            needed = allocation.get(profile.concept_id, 0)
            bank = await quiz_repository.list_questions_for_concept(
                profile.concept_id,
                profile.material_version,
            )
            missing = max(0, needed - len(bank))
            if missing > 0:
                buffer = max(_settings.quiz_bank_buffer, 0)
                generate_count = missing + buffer
                generated = await _generate_questions_for_concept(
                    engine=engine,
                    subject_id=subject.id,
                    subject_name=subject.name,
                    grade_level=subject.grade_level,
                    profile=profile,
                    count=generate_count,
                )
                if generated:
                    stored = await quiz_repository.create_questions(generated)
                    bank = [*bank, *stored]
            return _ConceptRuntime(
                profile=profile,
                weight=weights.get(profile.concept_id, 1.0),
                question_count=needed,
                questions=bank,
            )

    concept_runtime = await asyncio.gather(*[_prepare_concept(profile) for profile in profiles])

    # Adjust allocations if any concept does not have enough questions.
    available_map = {entry.profile.concept_id: len(entry.questions) for entry in concept_runtime}
    adjusted = dict(allocation)
    shortfall = 0
    for concept_id, count in adjusted.items():
        available = available_map.get(concept_id, 0)
        if count > available:
            shortfall += count - available
            adjusted[concept_id] = available
    if shortfall > 0:
        candidates = sorted(
            concept_runtime,
            key=lambda entry: available_map.get(entry.profile.concept_id, 0) - adjusted.get(entry.profile.concept_id, 0),
            reverse=True,
        )
        for entry in candidates:
            if shortfall <= 0:
                break
            concept_id = entry.profile.concept_id
            spare = available_map.get(concept_id, 0) - adjusted.get(concept_id, 0)
            if spare <= 0:
                continue
            take = min(spare, shortfall)
            adjusted[concept_id] = adjusted.get(concept_id, 0) + take
            shortfall -= take

    selected_questions: list[QuizQuestion] = []
    topic_summaries: list = []
    for entry in concept_runtime:
        concept_id = entry.profile.concept_id
        desired = adjusted.get(concept_id, 0)
        if desired <= 0 or not entry.questions:
            continue
        pool = entry.questions
        if len(pool) <= desired:
            chosen = list(pool)
        else:
            chosen = random.sample(pool, desired)
        selected_questions.extend(chosen)
        topic_summaries.append(
            quiz_service.QuizTopicSummary(
                concept_id=concept_id,
                concept_name=entry.profile.concept_name,
                weight=round(entry.weight, 3),
                question_count=desired,
                complexity_score=entry.profile.complexity_score,
            )
        )

    if not selected_questions:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Quiz questions are not available yet. Please try again shortly.",
        )

    random.shuffle(selected_questions)
    question_ids = [question.id for question in selected_questions]
    now = datetime.now(timezone.utc)
    session_model = QuizSession(
        user_id=user_id,
        subject_id=subject.id,
        status=QuizSessionStatus.in_progress,
        concept_ids=unique_ids,
        question_ids=question_ids,
        current_index=0,
        total_questions=len(question_ids),
        correct_count=0,
        incorrect_count=0,
        score_percent=None,
        session_meta={
            "target_count": target_count,
            "weights": {key: round(value, 3) for key, value in weights.items()},
            "topic_summaries": [summary.model_dump() for summary in topic_summaries],
            "first_attempt_correct": 0,
        },
        started_at=now,
        updated_at=now,
    )
    session_model = await quiz_repository.create_session(session_model)

    first_question = selected_questions[0]
    question_response = quiz_service.build_quiz_question_response(
        question_id=first_question.id,
        concept_id=first_question.concept_id,
        concept_name=concept_map[first_question.concept_id].name,
        question=first_question.question,
        options=list(first_question.options or [])[:4],
        difficulty=first_question.difficulty or "medium",
        position=1,
        total=len(question_ids),
    )
    session_response = quiz_service.build_session_response(
        session_id=session_model.id,
        subject_id=subject.id,
        subject_name=subject.name,
        status=session_model.status,
        total_questions=session_model.total_questions,
        current_index=session_model.current_index,
        correct_count=session_model.correct_count,
        incorrect_count=session_model.incorrect_count,
        first_attempt_correct_count=_first_attempt_count(session_model.session_meta),
        started_at=session_model.started_at,
        completed_at=session_model.completed_at,
        topics=topic_summaries,
    )

    return QuizSessionStartResponse(session=session_response, question=question_response)


async def get_student_quiz_session(session_id: str, user_id: str) -> QuizSessionStartResponse:
    session = await _get_session_for_user(session_id, user_id)
    subject = await study_material_repository.get_subject(session.subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found.")
    if not session.question_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session is empty.")
    concept_rows = await study_material_repository.list_concepts(session.subject_id)
    concept_map = {row.id: row for row in concept_rows}
    question_ids = list(session.question_ids or [])
    current_index = min(session.current_index, max(len(question_ids) - 1, 0))
    current_question_id = question_ids[current_index]
    question = await quiz_repository.get_question(current_question_id)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz question not found.")
    position = current_index + 1
    question_response = quiz_service.build_quiz_question_response(
        question_id=question.id,
        concept_id=question.concept_id,
        concept_name=concept_map.get(question.concept_id).name if concept_map.get(question.concept_id) else "Concept",
        question=question.question,
        options=list(question.options or [])[:4],
        difficulty=question.difficulty or "medium",
        position=position,
        total=len(question_ids),
    )
    session_response = quiz_service.build_session_response(
        session_id=session.id,
        subject_id=subject.id,
        subject_name=subject.name,
        status=session.status,
        total_questions=session.total_questions,
        current_index=session.current_index,
        correct_count=session.correct_count,
        incorrect_count=session.incorrect_count,
        first_attempt_correct_count=_first_attempt_count(session.session_meta),
        started_at=session.started_at,
        completed_at=session.completed_at,
        topics=_summaries_from_metadata(session.session_meta, concept_map),
    )
    return QuizSessionStartResponse(session=session_response, question=question_response)


async def submit_student_answer(
    session_id: str,
    user_id: str,
    payload: QuizAnswerRequest,
) -> QuizAnswerResponse:
    session = await _get_session_for_user(session_id, user_id)
    if session.status != QuizSessionStatus.in_progress:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quiz session is already completed.",
        )
    if not session.question_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session has no questions.")

    question_ids = list(session.question_ids)
    current_index = session.current_index
    if current_index >= len(question_ids):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quiz session already finished.")
    expected_question_id = question_ids[current_index]
    if payload.question_id != expected_question_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Answer does not match the current question.",
        )

    question = await quiz_repository.get_question(payload.question_id)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found.")
    selected_option = payload.selected_option.strip()
    options = [str(opt).strip() for opt in (question.options or []) if str(opt).strip()]
    if selected_option not in options:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected option is invalid for this question.",
        )

    correct_option = str(question.correct_option).strip()
    is_correct = selected_option == correct_option
    response = await quiz_repository.get_response(session.id, question.id)
    attempts = (response.attempts if response else 0) + 1
    hints_used = response.hints_used if response else 0
    if not is_correct:
        hints_used = min(attempts, _settings.quiz_max_hints)
    else:
        hints_used = response.hints_used if response else 0

    now = datetime.now(timezone.utc)
    attempt_log = list(response.attempt_log or []) if response else []
    attempt_log.append(
        {
            "selected_option": selected_option,
            "correct": is_correct,
            "hint_index": hints_used if not is_correct else None,
            "answered_at": now.isoformat(),
        }
    )

    response_model = QuizResponse(
        session_id=session.id,
        question_id=question.id,
        concept_id=question.concept_id,
        selected_option=selected_option,
        is_correct=is_correct,
        attempts=attempts,
        hints_used=hints_used,
        attempt_log=attempt_log,
        answered_at=now,
        created_at=response.created_at if response else now,
        updated_at=now,
    )
    if response:
        response_model.id = response.id
    await quiz_repository.upsert_response(response_model)

    hint_text = None
    if not is_correct:
        hints = list(question.hints or [])
        if attempts <= _settings.quiz_max_hints and hints_used <= len(hints):
            hint_text = hints[hints_used - 1]

    if is_correct:
        session.correct_count += 1
        session.current_index += 1
        if attempts == 1:
            meta = dict(session.session_meta or {})
            meta["first_attempt_correct"] = int(meta.get("first_attempt_correct", 0)) + 1
            session.session_meta = meta
    else:
        session.incorrect_count += 1

    completed = session.current_index >= len(question_ids)
    report: QuizReportResponse | None = None
    if completed:
        session.status = QuizSessionStatus.completed
        session.completed_at = now
        session.score_percent = round(
            (_first_attempt_count(session.session_meta) / session.total_questions) * 100,
            2,
        )
        report = await _build_and_store_report(session, question_ids)
    await quiz_repository.update_session(session)

    subject = await study_material_repository.get_subject(session.subject_id)
    subject_name = subject.name if subject else "Subject"
    concept_rows = await study_material_repository.list_concepts(session.subject_id)
    concept_map = {row.id: row for row in concept_rows}
    session_response = quiz_service.build_session_response(
        session_id=session.id,
        subject_id=session.subject_id,
        subject_name=subject_name,
        status=session.status,
        total_questions=session.total_questions,
        current_index=session.current_index,
        correct_count=session.correct_count,
        incorrect_count=session.incorrect_count,
        first_attempt_correct_count=_first_attempt_count(session.session_meta),
        started_at=session.started_at,
        completed_at=session.completed_at,
        topics=_summaries_from_metadata(session.session_meta, concept_map),
    )

    next_question = None
    if not completed and is_correct:
        next_index = session.current_index
        next_question_id = question_ids[next_index]
        next_question_obj = await quiz_repository.get_question(next_question_id)
        if next_question_obj:
            next_question = quiz_service.build_quiz_question_response(
                question_id=next_question_obj.id,
                concept_id=next_question_obj.concept_id,
                concept_name=concept_map.get(next_question_obj.concept_id).name
                if concept_map.get(next_question_obj.concept_id)
                else "Concept",
                question=next_question_obj.question,
                options=list(next_question_obj.options or [])[:4],
                difficulty=next_question_obj.difficulty or "medium",
                position=next_index + 1,
                total=len(question_ids),
            )

    remaining_hints = max(0, _settings.quiz_max_hints - hints_used) if not is_correct else _settings.quiz_max_hints
    return QuizAnswerResponse(
        correct=is_correct,
        hint=hint_text,
        hints_used=hints_used if not is_correct else 0,
        remaining_hints=remaining_hints if not is_correct else _settings.quiz_max_hints,
        session=session_response,
        next_question=next_question,
        completed=completed,
        report=report,
    )


async def get_student_quiz_report(session_id: str, user_id: str) -> QuizReportResponse:
    session = await _get_session_for_user(session_id, user_id)
    if session.status != QuizSessionStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quiz report is available only after completion.",
        )
    if session.report and _report_uses_first_attempt_scoring(session):
        report = QuizReportResponse(**session.report)
        return report
    question_ids = list(session.question_ids or [])
    report = await _build_and_store_report(session, question_ids)
    return report


async def _get_session_for_user(session_id: str, user_id: str) -> QuizSession:
    session = await quiz_repository.get_session(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found.")
    return session


def _summaries_from_metadata(metadata: dict | None, concept_map: dict) -> list:
    if not metadata:
        return []
    summaries = metadata.get("topic_summaries") or []
    if summaries:
        return [quiz_service.QuizTopicSummary(**item) for item in summaries]
    weights = metadata.get("weights") or {}
    fallback: list = []
    for concept_id, weight in weights.items():
        concept = concept_map.get(concept_id)
        if not concept:
            continue
        fallback.append(
            quiz_service.QuizTopicSummary(
                concept_id=concept_id,
                concept_name=concept.name,
                weight=float(weight),
                question_count=0,
                complexity_score=None,
            )
        )
    return fallback


def _first_attempt_count(metadata: dict | None) -> int:
    if not metadata:
        return 0
    return int(metadata.get("first_attempt_correct", 0) or 0)


async def _generate_questions_for_concept(
    *,
    engine: QuizEngine,
    subject_id: str,
    subject_name: str,
    grade_level: str,
    profile: quiz_service.ConceptProfile,
    count: int,
) -> list[QuizQuestion]:
    context = quiz_service.extract_quiz_context(profile.content)
    questions: list[QuizQuestion] = []
    remaining = count
    revision_feedback: str | None = None

    for attempt in range(2):
        if remaining <= 0:
            break
        mcqs = await asyncio.to_thread(
            engine.generate_mcqs,
            subject_name=subject_name,
            grade_level=grade_level,
            concept_name=profile.concept_name,
            concept_summary=context["summary"],
            key_points=context["key_points"],
            common_mistakes=context["common_mistakes"],
            question_count=remaining,
            revision_feedback=revision_feedback,
        )
        for item in mcqs or []:
            question = _normalize_mcq(item, profile=profile, subject_id=subject_id)
            if question:
                questions.append(question)
        remaining = count - len(questions)
        revision_feedback = "Ensure every MCQ has 4 unique options, a valid answer, and 3 safe hints."

    if len(questions) < count:
        logger.warning(
            "[QuizGeneration] Only %s/%s questions validated for concept '%s'.",
            len(questions),
            count,
            profile.concept_name,
        )
    return questions


def _normalize_mcq(item: Any, *, profile: quiz_service.ConceptProfile, subject_id: str) -> QuizQuestion | None:
    if not isinstance(item, dict):
        return None
    question_text = str(item.get("question", "")).strip()
    if len(question_text) < 10:
        return None
    raw_options = item.get("options") or []
    options = [str(opt).strip() for opt in raw_options if str(opt).strip()]
    options = list(dict.fromkeys(options))
    if len(options) != 4:
        return None
    answer = str(item.get("answer", "")).strip()
    if not answer:
        return None
    if answer not in options:
        normalized = {opt.lower(): opt for opt in options}
        if answer.lower() in normalized:
            answer = normalized[answer.lower()]
        else:
            return None

    difficulty = str(item.get("difficulty", "medium")).strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    hints = item.get("hints") or []
    hints_list = [str(hint).strip() for hint in hints if str(hint).strip()]
    sanitized_hints = quiz_service.sanitize_hints(
        hints=hints_list,
        answer=answer,
        concept_name=profile.concept_name,
        question=question_text,
    )

    explanation = str(item.get("explanation", "")).strip() or None

    if not subject_id:
        return None
    return QuizQuestion(
        subject_id=subject_id,
        concept_id=profile.concept_id,
        material_version=profile.material_version,
        question=question_text,
        options=options,
        correct_option=answer,
        hints=sanitized_hints,
        explanation=explanation,
        difficulty=difficulty,
    )


async def _build_and_store_report(session: QuizSession, question_ids: list[str]) -> QuizReportResponse:
    subject = await study_material_repository.get_subject(session.subject_id)
    subject_name = subject.name if subject else "Subject"
    concept_rows = await study_material_repository.list_concepts(session.subject_id)
    concept_map = {row.id: row for row in concept_rows}
    responses = await quiz_repository.list_responses_by_session(session.id)
    response_map: dict[str, list[QuizResponse]] = {}
    for response in responses:
        response_map.setdefault(response.concept_id, []).append(response)

    first_attempt_correct_count = sum(
        1 for response in responses if _was_first_attempt_correct(response)
    )
    total_attempts = sum(int(response.attempts or 0) for response in responses)

    topic_performance: list = []
    for concept_id in session.concept_ids or []:
        concept = concept_map.get(concept_id)
        if not concept:
            continue
        responses_for_topic = response_map.get(concept_id, [])
        first_attempt_correct = sum(
            1 for item in responses_for_topic if _was_first_attempt_correct(item)
        )
        total_questions = len(responses_for_topic)
        highlights: list[str] = []
        material = await study_material_repository.get_latest_material(concept_id, published_only=True)
        if material and material.content:
            content = LearningContent(**material.content)
            highlights = list(content.highlights or [])[:2]
        topic_performance.append(
            quiz_service.build_topic_performance(
                concept_id=concept_id,
                concept_name=concept.name,
                first_attempt_correct_count=first_attempt_correct,
                total_questions=total_questions,
                highlights=highlights,
            )
        )

    report = quiz_service.build_report(
        session_id=session.id,
        subject_id=session.subject_id,
        subject_name=subject_name,
        total_questions=session.total_questions,
        first_attempt_correct_count=first_attempt_correct_count,
        completed_at=session.completed_at or datetime.now(timezone.utc),
        topic_performance=topic_performance,
        metadata={
            "attempted_questions": len(responses),
            "total_attempts": total_attempts,
            "resolved_questions": session.correct_count,
            "first_attempt_correct_count": first_attempt_correct_count,
            "scoring_model": "first_attempt_accuracy",
        },
    )
    session.report = report.model_dump(mode="json")
    await quiz_repository.update_session(session)
    return report


def _was_first_attempt_correct(response: QuizResponse) -> bool:
    attempt_log = list(response.attempt_log or [])
    if attempt_log:
        first_attempt = attempt_log[0]
        if isinstance(first_attempt, dict):
            return bool(first_attempt.get("correct"))
    return bool(response.is_correct and int(response.attempts or 0) <= 1)


def _report_uses_first_attempt_scoring(session: QuizSession) -> bool:
    if not isinstance(session.report, dict):
        return False
    meta = session.report.get("meta")
    if not isinstance(meta, dict):
        return False
    return meta.get("scoring_model") == "first_attempt_accuracy"
