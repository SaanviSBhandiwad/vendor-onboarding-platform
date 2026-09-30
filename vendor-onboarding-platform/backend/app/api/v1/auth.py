from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token
from app.schemas.common import error_responses
from app.schemas.user import Token, UserRead, UserRegister
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserRead, status_code=status.HTTP_201_CREATED,
    responses=error_responses(409),
)
def register(payload: UserRegister, db: DbSession) -> UserRead:
    """Create a vendor account. Staff accounts are created by an admin via /users."""
    return user_service.register_vendor_user(db, payload)


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token:
    """OAuth2 password flow. Put the account **email** in the `username` field."""
    user = user_service.authenticate(db, form.username, form.password)
    if user is None:
        # Same message for unknown email, wrong password and inactive account.
        raise UnauthorizedError("Incorrect email or password")
    token, expires_in = create_access_token(str(user.id), user.role.value)
    return Token(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> UserRead:
    return user
