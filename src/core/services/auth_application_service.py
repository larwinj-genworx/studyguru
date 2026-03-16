from __future__ import annotations

from fastapi import HTTPException, status

from src.core.services.auth_service import create_access_token
from src.data.repositories import auth_repository
from src.schemas.auth import LoginRequest, TokenResponse, UserResponse


def _to_user_response(user) -> UserResponse:
    return UserResponse(
        user_id=user.id,
        email=user.email,
        role=user.role,
        organization_id=user.organization_id,
    )


async def login(payload: LoginRequest) -> TokenResponse:
    user = await auth_repository.verify_user_credentials(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    organization = await auth_repository.get_organization_by_id(user.organization_id)
    if not organization or not organization.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Organization not found.")
    token = create_access_token(
        {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "organization_id": user.organization_id,
        }
    )
    return TokenResponse(
        access_token=token,
        user=_to_user_response(user),
    )
