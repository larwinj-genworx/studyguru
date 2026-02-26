from __future__ import annotations

from fastapi import Header, HTTPException, status


def require_role(expected_role: str):
    async def _require_role(x_role: str | None = Header(default=None, alias="X-Role")) -> None:
        if (x_role or "").strip().lower() != expected_role.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"X-Role '{expected_role}' is required.",
            )

    return _require_role
