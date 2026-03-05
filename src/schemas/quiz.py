from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QuizSessionStatus(str, Enum):
    in_progress = "in_progress"
    completed = "completed"
    abandoned = "abandoned"


class QuizSessionStartRequest(BaseModel):
    subject_id: str
    concept_ids: list[str] = Field(min_length=1, max_length=30)


class QuizAnswerRequest(BaseModel):
    question_id: str
    selected_option: str = Field(min_length=1, max_length=400)


class QuizTopicSummary(BaseModel):
    concept_id: str
    concept_name: str
    weight: float
    question_count: int
    complexity_score: float | None = None


class QuizSessionResponse(BaseModel):
    session_id: str
    subject_id: str
    subject_name: str
    status: QuizSessionStatus
    total_questions: int
    current_index: int
    correct_count: int
    incorrect_count: int
    first_attempt_correct_count: int
    started_at: datetime
    completed_at: datetime | None = None
    topics: list[QuizTopicSummary] = Field(default_factory=list)


class QuizQuestionResponse(BaseModel):
    question_id: str
    concept_id: str
    concept_name: str
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    difficulty: str = "medium"
    position: int
    total: int


class QuizSessionStartResponse(BaseModel):
    session: QuizSessionResponse
    question: QuizQuestionResponse


class QuizTopicPerformance(BaseModel):
    concept_id: str
    concept_name: str
    accuracy: float
    correct_count: int
    total_questions: int
    status: str
    recommendations: list[str] = Field(default_factory=list)


class QuizReportResponse(BaseModel):
    session_id: str
    subject_id: str
    subject_name: str
    total_questions: int
    correct_count: int
    accuracy: float
    completed_at: datetime
    topic_breakdown: list[QuizTopicPerformance] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class QuizAnswerResponse(BaseModel):
    correct: bool
    hint: str | None = None
    hints_used: int = 0
    remaining_hints: int = 0
    session: QuizSessionResponse
    next_question: QuizQuestionResponse | None = None
    completed: bool = False
    report: QuizReportResponse | None = None
