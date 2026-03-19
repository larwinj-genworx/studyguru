from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, status

from src.config.settings import Settings
from src.schemas.concept_visual_microservice import (
    ConceptVisualRenderRequest,
    ConceptVisualRenderResponse,
)

logger = logging.getLogger(__name__)


class ConceptVisualMicroserviceClient:
    """HTTP client for the concept visual generation microservice."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def render(self, payload: ConceptVisualRenderRequest) -> ConceptVisualRenderResponse:
        """Render concept visuals through the dedicated microservice."""

        base_url = self.settings.concept_visual_service_url.strip()
        if not base_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CONCEPT_VISUAL_SERVICE_URL is not configured.",
            )
        if not self.settings.concept_visual_service_token.strip():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CONCEPT_VISUAL_SERVICE_TOKEN is not configured.",
            )
        timeout = httpx.Timeout(
            connect=5.0,
            read=max(float(self.settings.concept_visual_request_timeout_seconds), 10.0),
            write=10.0,
            pool=5.0,
        )
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
            ) as client:
                response = await client.post(
                    f"{base_url.rstrip('/')}/v1/concept-visuals/render",
                    json=payload.model_dump(mode="json"),
                    headers={
                        "X-StudyGuru-Service-Token": self.settings.concept_visual_service_token.strip(),
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Concept visual service returned an HTTP error.", exc_info=True)
            detail = exc.response.text.strip() or "Concept visual service failed."
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
        except httpx.HTTPError as exc:
            logger.error("Concept visual service call failed.", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Concept visual service is unavailable.",
            ) from exc

        try:
            return ConceptVisualRenderResponse(**response.json())
        except ValueError as exc:
            logger.error("Concept visual service returned an invalid payload.", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Concept visual service returned an invalid response.",
            ) from exc
