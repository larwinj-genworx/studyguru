from fastapi import APIRouter, Response, status

from src.core.services.health_service import build_health_response
from src.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/", response_model=HealthResponse)
async def health_check(response: Response) -> HealthResponse:
    """Run readiness checks for Cloud Run and operational monitoring."""

    report = await build_health_response()
    response.status_code = (
        status.HTTP_200_OK
        if report.status == "ok"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return report


@router.get("/live")
async def liveness_check() -> dict[str, str]:
    """Return a lightweight liveness response without dependency checks."""

    return {"status": "ok"}
