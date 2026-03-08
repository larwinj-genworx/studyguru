from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LearningBotSessionStatus(str, Enum):
    active = "active"
    archived = "archived"


class LearningBotMessageRole(str, Enum):
    user = "user"
    assistant = "assistant"


class LearningBotCitation(BaseModel):
    source_id: str
    label: str
    source_type: str
    url: str | None = None
    section_id: str | None = None
    note: str | None = None


class LearningBotMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class LearningBotMessageResponse(BaseModel):
    message_id: str
    role: LearningBotMessageRole
    content: str
    citations: list[LearningBotCitation] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class LearningBotSessionResponse(BaseModel):
    session_id: str
    subject_id: str
    subject_name: str
    concept_id: str
    concept_name: str
    grade_level: str
    status: LearningBotSessionStatus
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class LearningBotSessionDetailResponse(BaseModel):
    session: LearningBotSessionResponse
    messages: list[LearningBotMessageResponse] = Field(default_factory=list)
    suggested_prompts: list[str] = Field(default_factory=list)


class LearningBotTurnResponse(BaseModel):
    session: LearningBotSessionResponse
    user_message: LearningBotMessageResponse
    assistant_message: LearningBotMessageResponse
