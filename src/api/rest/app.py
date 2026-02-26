from fastapi import APIRouter
from .routes import health
from .routes import study_material_generation

api_routers = APIRouter()

# Defining all the routes 
api_routers.include_router(health.router)
api_routers.include_router(
    study_material_generation.router,
    prefix="/v1/study-material",
    tags=["study-material"],
)
api_routers.include_router(
    study_material_generation.router,
    prefix="/temp/v1",
    include_in_schema=False,
)
