from __future__ import annotations

from fastapi import HTTPException, status

from src.core.services.auth_service import create_access_token
from src.data.repositories import auth_repository
from src.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse


async def signup(payload: SignupRequest) -> TokenResponse:
    existing = await auth_repository.get_user_by_email(payload.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    user = await auth_repository.create_user(payload.email, payload.password, payload.role)
    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse(user_id=user.id, email=user.email, role=user.role),
    )


async def login(payload: LoginRequest) -> TokenResponse:
    user = await auth_repository.verify_user_credentials(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return TokenResponse(
        access_token=token,
        user=UserResponse(user_id=user.id, email=user.email, role=user.role),
    )
