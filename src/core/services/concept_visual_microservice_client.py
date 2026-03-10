from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from src.config.settings import Settings
from src.schemas.concept_visual_microservice import (
    ConceptVisualRenderRequest,
    ConceptVisualRenderResponse,
)


class ConceptVisualMicroserviceClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def render(self, payload: ConceptVisualRenderRequest) -> ConceptVisualRenderResponse:
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
                    f"{self.settings.concept_visual_service_url.rstrip('/')}/v1/concept-visuals/render",
                    json=payload.model_dump(mode="json"),
                    headers={
                        "X-StudyGuru-Service-Token": self.settings.concept_visual_service_token,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or "Concept visual service failed."
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Concept visual service is unavailable.",
            ) from exc

        return ConceptVisualRenderResponse(**response.json())
