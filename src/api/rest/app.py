from fastapi import APIRouter
from .routes import health
from .routes import temp_agentic

api_routers = APIRouter()

# Defining all the routes 
api_routers.include_router(health.router)
api_routers.include_router(temp_agentic.router)
