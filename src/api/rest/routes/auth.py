from fastapi import APIRouter

from src.core.services import auth_application_service
from src.schemas.auth import LoginRequest, SignupRequest, TokenResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(payload: SignupRequest) -> TokenResponse:
    return await auth_application_service.signup(payload)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    return await auth_application_service.login(payload)
