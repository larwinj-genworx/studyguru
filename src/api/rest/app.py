from fastapi import APIRouter
from .routes import auth, health, study_material, quiz

api_routers = APIRouter()

# Defining all the routes 
api_routers.include_router(health.router)
api_routers.include_router(auth.router)
api_routers.include_router(
    study_material.router,
    prefix="/v1/study-material",
    tags=["study-material"],
)
api_routers.include_router(
    quiz.router,
    prefix="/v1/quizzes",
    tags=["quiz"],
)
