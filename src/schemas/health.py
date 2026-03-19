from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthCheckResult(BaseModel):
    """Structured status for a single dependency check."""

    status: Literal["ok", "error"]
    detail: str
    latency_ms: float | None = Field(default=None, ge=0)


class HealthResponse(BaseModel):
    """Readiness payload returned by service health endpoints."""

    status: Literal["ok", "error"]
    service: str
    version: str
    checks: dict[str, HealthCheckResult] = Field(default_factory=dict)
