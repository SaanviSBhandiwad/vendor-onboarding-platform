import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VendorStatus(enum.StrEnum):
    PENDING = "PENDING"                          # registered, waiting for documents
    DOCUMENTS_SUBMITTED = "DOCUMENTS_SUBMITTED"  # documents uploaded, queued for processing
    UNDER_REVIEW = "UNDER_REVIEW"                # automated compliance check running
    MANUAL_REVIEW = "MANUAL_REVIEW"              # low-confidence result, routed to a human
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in VendorStatus)


class Vendor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        # Uniqueness is enforced by the database, not only by application code,
        # so concurrent registrations cannot create duplicates.
        UniqueConstraint("email", name="uq_vendors_email"),
        UniqueConstraint("gstin", name="uq_vendors_gstin"),
        # One vendor profile per vendor user account.
        UniqueConstraint("owner_id", name="uq_vendors_owner_id"),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="valid_status"),
        Index("ix_vendors_status", "status"),
        Index("ix_vendors_region", "region"),
        Index("ix_vendors_created_at", "created_at"),
    )

    # Nullable: vendors created before accounts existed (or by staff) have no owner.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    service_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[VendorStatus] = mapped_column(
        Enum(VendorStatus, native_enum=False, length=32, create_constraint=False, validate_strings=True),
        nullable=False,
        default=VendorStatus.PENDING,
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
