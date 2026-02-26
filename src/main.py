from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.rest.app import api_routers


app = FastAPI(
    title="StudyGuru API",
    description="Study material generation APIs.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_routers)


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"service": "StudyGuru API", "status": "running"}
