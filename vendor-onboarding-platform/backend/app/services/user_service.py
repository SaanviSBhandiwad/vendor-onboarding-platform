import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateUserError, NotFoundError, SelfLockoutError
from app.core.security import hash_password, verify_password
from app.models import User, UserRole
from app.schemas.user import UserCreate, UserRegister, UserUpdate
from app.services import audit_service

logger = logging.getLogger(__name__)
ENTITY = "user"


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email.strip().lower())).first()


def _create(db: Session, *, email: str, full_name: str, password: str, role: UserRole, actor: str) -> User:
    if get_by_email(db, email) is not None:
        raise DuplicateUserError("An account with this email already exists", details={"fields": ["email"]})
    user = User(email=email, full_name=full_name, hashed_password=hash_password(password), role=role)
    db.add(user)
    try:
        db.flush()
        audit_service.record(
            db, entity_type=ENTITY, entity_id=user.id, action="user_created", actor=actor,
            details={"role": role.value},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateUserError(
            "An account with this email already exists", details={"fields": ["email"]}
        ) from exc
    db.refresh(user)
    logger.info("user_created", extra={"user_id": str(user.id), "role": role.value})
    return user


def register_vendor_user(db: Session, data: UserRegister) -> User:
    user = _create(
        db, email=data.email, full_name=data.full_name, password=data.password,
        role=UserRole.VENDOR, actor="self-registration",
    )
    return user


def create_user(db: Session, data: UserCreate, actor: str) -> User:
    return _create(
        db, email=data.email, full_name=data.full_name, password=data.password, role=data.role, actor=actor
    )


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = get_by_email(db, email)
    # verify_password runs even when the user is missing (dummy hash) to keep timing uniform.
    if not verify_password(password, user.hashed_password if user else None):
        return None
    if user is None or not user.is_active:
        return None
    return user


def get_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found", details={"user_id": str(user_id)})
    return user


def list_users(
    db: Session, *, role: UserRole | None = None, limit: int = 20, offset: int = 0
) -> tuple[list[User], int]:
    filters = [User.role == role] if role else []
    total = db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    stmt = select(User).where(*filters).order_by(User.created_at.desc(), User.id).limit(limit).offset(offset)
    return list(db.scalars(stmt)), total


def update_user(db: Session, user_id: uuid.UUID, data: UserUpdate, *, current: User, actor: str) -> User:
    user = get_user(db, user_id)
    changes = data.model_dump(exclude_unset=True)

    # Guard against an admin locking themselves (and possibly everyone) out.
    if user.id == current.id and (
        changes.get("is_active") is False or ("role" in changes and changes["role"] != UserRole.ADMIN)
    ):
        raise SelfLockoutError("You cannot deactivate or demote your own account")

    before = {k: getattr(user, k) for k in changes}
    for key, value in changes.items():
        setattr(user, key, value)
    audit_service.record(
        db, entity_type=ENTITY, entity_id=user.id, action="user_updated", actor=actor,
        details={
            "before": {k: getattr(v, "value", v) for k, v in before.items()},
            "after": {k: getattr(v, "value", v) for k, v in changes.items()},
        },
    )
    db.commit()
    db.refresh(user)
    return user
