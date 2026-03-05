from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.api.rest.dependencies import get_current_user, require_role
from src.core.services import quiz_app_service
from src.schemas.quiz import (
    QuizAnswerRequest,
    QuizAnswerResponse,
    QuizReportResponse,
    QuizSessionResponse,
    QuizSessionStartRequest,
    QuizSessionStartResponse,
)

router = APIRouter(tags=["quiz"])


@router.post(
    "/student/sessions",
    response_model=QuizSessionStartResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("student"))],
)
async def start_quiz_session(
    payload: QuizSessionStartRequest,
    current_user: dict = Depends(get_current_user),
) -> QuizSessionStartResponse:
    return await quiz_app_service.start_student_quiz(payload, user_id=current_user["id"])


@router.get(
    "/student/sessions/{session_id}",
    response_model=QuizSessionStartResponse,
    dependencies=[Depends(require_role("student"))],
)
async def get_quiz_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> QuizSessionStartResponse:
    return await quiz_app_service.get_student_quiz_session(session_id, user_id=current_user["id"])


@router.post(
    "/student/sessions/{session_id}/answer",
    response_model=QuizAnswerResponse,
    dependencies=[Depends(require_role("student"))],
)
async def submit_quiz_answer(
    session_id: str,
    payload: QuizAnswerRequest,
    current_user: dict = Depends(get_current_user),
) -> QuizAnswerResponse:
    return await quiz_app_service.submit_student_answer(
        session_id=session_id,
        user_id=current_user["id"],
        payload=payload,
    )


@router.get(
    "/student/sessions/{session_id}/report",
    response_model=QuizReportResponse,
    dependencies=[Depends(require_role("student"))],
)
async def get_quiz_report(
    session_id: str,
    current_user: dict = Depends(get_current_user),
) -> QuizReportResponse:
    return await quiz_app_service.get_student_quiz_report(session_id, user_id=current_user["id"])
