from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from src.config.settings import get_settings
from src.core.services.auth_service import decode_access_token
from src.data.repositories import auth_repository


def _resolve_access_token(request: Request, authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()

    settings = get_settings()
    token = request.cookies.get(settings.auth_cookie_name)
    if token:
        return token

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token.")


async def get_current_user(request: Request, authorization: str | None = Header(default=None)) -> dict:
    token = _resolve_access_token(request, authorization)
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
    async def _require_role(request: Request, authorization: str | None = Header(default=None)) -> None:
        current_user = await get_current_user(request, authorization)
        if current_user["role"].lower() != expected_role.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{expected_role}' is required.",
            )

    return _require_role
