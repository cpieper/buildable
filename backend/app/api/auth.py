from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_request_settings, require_auth
from app.config import Settings
from app.db import get_session
from app.schemas.auth import LoginRequest, PasswordChangeRequest, SessionResponse
from app.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    PasswordStore,
    SessionSigner,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def set_session_cookie(
    response: Response,
    *,
    settings: Settings,
    revision: int,
    credential_binding: str,
) -> None:
    token = SessionSigner(
        settings.session_secret,
        credential_binding,
    ).create(revision)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
        path="/",
    )


def invalid_password() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid password",
    )


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    password_store = PasswordStore(session)
    revision = password_store.revision()
    credential_binding = password_store.session_binding()
    if (
        not password_store.verify(payload.password)
        or revision is None
        or credential_binding is None
    ):
        raise invalid_password()
    set_session_cookie(
        response,
        settings=get_request_settings(request),
        revision=revision,
        credential_binding=credential_binding,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, request: Request) -> None:
    settings = get_request_settings(request)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


@router.get(
    "/session",
    response_model=SessionResponse,
    dependencies=[Depends(require_auth)],
)
def session_status() -> SessionResponse:
    return SessionResponse(authenticated=True)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_auth)],
)
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    password_store = PasswordStore(session)
    if not password_store.verify(payload.current_password):
        raise invalid_password()
    revision = password_store.set_password(payload.new_password)
    credential_binding = password_store.session_binding()
    if credential_binding is None:
        raise RuntimeError("Password hash missing after password change")
    set_session_cookie(
        response,
        settings=get_request_settings(request),
        revision=revision,
        credential_binding=credential_binding,
    )
