from __future__ import annotations

import asyncio
import logging
from time import perf_counter

import httpx
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.config.settings import Settings, get_settings
from src.data.clients.postgres import engine
from src.schemas.health import HealthCheckResult, HealthResponse

logger = logging.getLogger(__name__)

_SERVICE_NAME = "StudyGuru API"
_SERVICE_VERSION = "0.1.0"


async def build_health_response(settings: Settings | None = None) -> HealthResponse:
    """Run service readiness checks for Cloud Run and operators."""

    active_settings = settings or get_settings()
    database_check, llm_check = await asyncio.gather(
        _check_database(),
        _check_llm_provider(active_settings),
    )
    checks = {
        "database": database_check,
        "llm": llm_check,
    }
    overall_status = "ok" if all(item.status == "ok" for item in checks.values()) else "error"
    return HealthResponse(
        status=overall_status,
        service=_SERVICE_NAME,
        version=_SERVICE_VERSION,
        checks=checks,
    )


async def _check_database() -> HealthCheckResult:
    started_at = perf_counter()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.error("Database health check failed.", exc_info=True)
        return HealthCheckResult(
            status="error",
            detail="Database connection check failed.",
            latency_ms=_elapsed_ms(started_at),
        )
    return HealthCheckResult(
        status="ok",
        detail="Database connection is healthy.",
        latency_ms=_elapsed_ms(started_at),
    )


async def _check_llm_provider(settings: Settings) -> HealthCheckResult:
    if not settings.groq_api.strip():
        return HealthCheckResult(
            status="error",
            detail="GROQ_API or GROQ_API_KEY is not configured.",
        )

    started_at = perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_healthcheck_timeout_seconds),
            follow_redirects=True,
        ) as client:
            response = await client.get(
                settings.groq_models_url,
                headers={"Authorization": f"Bearer {settings.groq_api.strip()}"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError:
        logger.error("LLM health check returned a non-success status.", exc_info=True)
        return HealthCheckResult(
            status="error",
            detail="LLM provider rejected the health check request.",
            latency_ms=_elapsed_ms(started_at),
        )
    except httpx.HTTPError:
        logger.error("LLM health check failed to reach the provider.", exc_info=True)
        return HealthCheckResult(
            status="error",
            detail="LLM provider is unavailable.",
            latency_ms=_elapsed_ms(started_at),
        )

    return HealthCheckResult(
        status="ok",
        detail="LLM provider is reachable.",
        latency_ms=_elapsed_ms(started_at),
    )


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)
