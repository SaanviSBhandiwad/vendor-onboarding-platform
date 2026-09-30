"""Password hashing (Argon2) and JWT access tokens."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_password_hash = PasswordHash.recommended()  # Argon2id

# Used when a login email does not exist, so the response takes the same time
# as a wrong password and attackers cannot enumerate registered emails.
_DUMMY_HASH = _password_hash.hash("timing-attack-mitigation-dummy-password")

ACCESS_TOKEN_TYPE = "access"


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if hashed is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, hashed)


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> tuple[str, int]:
    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,  # informational only; authorization always uses the role stored in the DB
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.InvalidTokenError (incl. ExpiredSignatureError) if the token is not valid."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],  # pinned: never trust the alg in the token header
        options={"require": ["exp", "iat", "sub"]},
    )
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Wrong token type")
    return payload
