from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class PlatformAdminProvisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    organization_name: str = Field(min_length=2, max_length=120)
    admin_email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class ManagedStudentSubjectResponse(BaseModel):
    subject_id: str
    name: str
    published: bool


class AdminManagedStudentCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class AdminManagedStudentUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    password: str | None = Field(default=None, min_length=6, max_length=128)
    is_active: bool | None = None


class UserResponse(BaseModel):
    user_id: str
    email: EmailStr
    role: str
    organization_id: str


class AdminManagedStudentResponse(BaseModel):
    user_id: str
    email: EmailStr
    role: Literal["student"] = "student"
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    assigned_subjects: list[ManagedStudentSubjectResponse] = Field(default_factory=list)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class SessionResponse(BaseModel):
    user: UserResponse
