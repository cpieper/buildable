from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_session
from app.services.auth import SESSION_COOKIE_NAME, PasswordStore, SessionSigner


def get_request_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_auth(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token_revision = SessionSigner(
        get_request_settings(request).session_secret
    ).read(token)
    stored_revision = PasswordStore(session).revision()
    if token_revision is None or token_revision != stored_revision:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
