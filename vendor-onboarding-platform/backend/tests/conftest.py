import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Base, User, UserRole

PASSWORD = "Passw0rd123"
_PASSWORD_HASH = hash_password(PASSWORD)  # hash once; Argon2 is deliberately slow


@pytest.fixture
def db_session():
    # Fast in-memory DB for unit/API tests. CI also runs migrations against real PostgreSQL.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session):
    def _make(role: UserRole = UserRole.VENDOR, *, email: str | None = None, active: bool = True) -> User:
        user = User(
            email=email or f"{role.value.lower()}-{uuid.uuid4().hex[:8]}@test.in",
            full_name=f"Test {role.value.title()}",
            hashed_password=_PASSWORD_HASH,
            role=role,
            is_active=active,
        )
        db_session.add(user)
        db_session.commit()
        return user

    return _make


def auth(user: User) -> dict[str, str]:
    token, _ = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def vendor_user(make_user):
    return make_user(UserRole.VENDOR)


@pytest.fixture
def other_vendor_user(make_user):
    return make_user(UserRole.VENDOR)


@pytest.fixture
def ops_user(make_user):
    return make_user(UserRole.OPERATIONS)


@pytest.fixture
def admin_user(make_user):
    return make_user(UserRole.ADMIN)


@pytest.fixture
def vendor_payload():
    return {
        "legal_name": "MediSupply  Pvt Ltd",
        "email": "Ops@MediSupply.in",
        "gstin": "27aapfu0939f1zv",
        "contact_phone": "+919876543210",
        "region": "West",
        "service_type": "Medical Equipment",
    }


@pytest.fixture
def other_vendor_payload():
    return {
        "legal_name": "CareParts Ltd",
        "email": "hello@careparts.in",
        "gstin": "29AABCU9603R1ZM",
        "region": "South",
        "service_type": "Consumables",
    }
