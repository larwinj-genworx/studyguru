from fastapi import FastAPI

from src.api.rest.app import api_routers


app = FastAPI(
    title="StudyGuru Temp Agentic API",
    description="Temporary CrewAI + LangGraph study-material generation APIs.",
    version="0.1.0",
)

app.include_router(api_routers)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"service": "StudyGuru Temp Agentic API", "status": "running"}
