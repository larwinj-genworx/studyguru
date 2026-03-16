from fastapi import APIRouter, Depends, Response, status

from src.api.rest.dependencies import get_current_user
from src.config.settings import get_settings
from src.core.services import auth_application_service
from src.schemas.auth import LoginRequest, SessionResponse, SignupRequest, TokenResponse, UserResponse


router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    max_age = settings.jwt_exp_minutes * 60
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max_age,
        expires=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        domain=settings.auth_cookie_domain or None,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        domain=settings.auth_cookie_domain or None,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        httponly=True,
    )


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(payload: SignupRequest, response: Response) -> TokenResponse:
    result = await auth_application_service.signup(payload)
    _set_auth_cookie(response, result.access_token)
    return result


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response) -> TokenResponse:
    result = await auth_application_service.login(payload)
    _set_auth_cookie(response, result.access_token)
    return result


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    _clear_auth_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/session", response_model=SessionResponse)
async def get_session(current_user: dict = Depends(get_current_user)) -> SessionResponse:
    return SessionResponse(
        user=UserResponse(
            user_id=current_user["id"],
            email=current_user["email"],
            role=current_user["role"],
        )
    )
