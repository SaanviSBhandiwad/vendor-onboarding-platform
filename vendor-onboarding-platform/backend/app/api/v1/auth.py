from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.core.logging import request_id_ctx
from app.core.security import create_access_token
from app.schemas.common import error_responses
from app.schemas.user import Token, UserRead, UserRegister
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


class OAuthError(BaseModel):
    """RFC 6749 section 5.2 error shape, used only by the token endpoint."""

    error: str
    error_description: str
    request_id: str | None


@router.post(
    "/register", response_model=UserRead, status_code=status.HTTP_201_CREATED,
    responses=error_responses(409),
)
def register(payload: UserRegister, db: DbSession) -> UserRead:
    """Create a vendor account. Staff accounts are created by an admin via /users."""
    return user_service.register_vendor_user(db, payload)


@router.post(
    "/login", response_model=Token,
    responses={401: {"model": OAuthError, "description": "Incorrect email or password"}},
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token | JSONResponse:
    """OAuth2 password flow. Put the account **email** in the `username` field."""
    user = user_service.authenticate(db, form.username, form.password)
    if user is None:
        # Same message for unknown email, wrong password and inactive account.
        # OAuth2 clients (including Swagger's Authorize box) expect this exact shape.
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
            content={"error": "invalid_grant", "error_description": "Incorrect email or password",
                     "request_id": request_id_ctx.get()},
        )
    token, expires_in = create_access_token(str(user.id), user.role.value)
    return Token(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> UserRead:
    return user
