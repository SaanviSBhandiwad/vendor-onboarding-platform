import enum

from sqlalchemy import Boolean, CheckConstraint, Enum, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(enum.StrEnum):
    VENDOR = "VENDOR"          # submits and tracks their own application
    OPERATIONS = "OPERATIONS"  # reviews applications and AI flags
    ADMIN = "ADMIN"            # manages users, policies and audit information


_ROLE_VALUES = ", ".join(f"'{r.value}'" for r in UserRole)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(f"role IN ({_ROLE_VALUES})", name="valid_role"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16, create_constraint=False, validate_strings=True),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
