from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import DEV_SECRET_KEY, Settings, get_settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("S3cretpass")
    assert h != "S3cretpass" and h.startswith("$argon2")
    assert verify_password("S3cretpass", h)
    assert not verify_password("wrong-pass1", h)


def test_verify_without_hash_is_false():
    assert verify_password("anything1", None) is False


def test_token_roundtrip():
    token, expires_in = create_access_token("abc", "VENDOR")
    payload = decode_access_token(token)
    assert payload["sub"] == "abc" and payload["type"] == "access"
    assert expires_in == get_settings().access_token_expire_minutes * 60


def test_expired_token_rejected():
    token, _ = create_access_token("abc", "VENDOR", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_other_key_rejected():
    s = get_settings()
    forged = jwt.encode(
        {"sub": "abc", "type": "access", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "attacker-key-" + "x" * 40, algorithm=s.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_unsigned_alg_none_token_rejected():
    forged = jwt.encode({"sub": "abc", "type": "access", "iat": 1, "exp": 9999999999}, None, algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)


def test_wrong_token_type_rejected():
    s = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode({"sub": "abc", "type": "refresh", "iat": now, "exp": now + timedelta(minutes=5)},
                       s.secret_key, algorithm=s.jwt_algorithm)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_default_secret_refused_in_production():
    with pytest.raises(ValidationError, match="SECRET_KEY must be set"):
        Settings(environment="production", secret_key=DEV_SECRET_KEY)
    Settings(environment="production", secret_key="a-real-production-secret-" + "x" * 20)


def test_short_secret_refused():
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(secret_key="short")
