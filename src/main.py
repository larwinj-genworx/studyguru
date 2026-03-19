import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.rest.app import api_routers
from src.config.settings import get_settings
from src.core.logging import configure_logging
from src.data.clients.postgres import init_db

settings = get_settings()
configure_logging(settings, service_name="studyguru-backend")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="StudyGuru API",
    description="Study material generation APIs.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_routers)

@app.on_event("startup")
async def startup_event() -> None:
    logger.info("Initializing backend services.")
    await init_db()
    logger.info("Backend startup completed successfully.")

@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Return a lightweight service metadata payload."""

    return {"service": "StudyGuru API", "status": "running"}
