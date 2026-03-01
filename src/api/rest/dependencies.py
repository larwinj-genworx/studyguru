from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.core.services.auth_service import decode_access_token
from src.data.repositories import auth_repository


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
    user = await auth_repository.get_user_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    return {"id": user.id, "email": user.email, "role": user.role}


def require_role(expected_role: str):
    async def _require_role(authorization: str | None = Header(default=None)) -> None:
        current_user = await get_current_user(authorization)
        if current_user["role"].lower() != expected_role.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{expected_role}' is required.",
            )

    return _require_role
