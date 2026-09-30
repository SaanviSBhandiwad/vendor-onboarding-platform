import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobType(enum.StrEnum):
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"


class JobStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def _in(values: type[enum.StrEnum]) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable record of background work. The Celery task id equals this row's id."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(f"job_type IN ({_in(JobType)})", name="valid_job_type"),
        CheckConstraint(f"status IN ({_in(JobStatus)})", name="valid_status"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_vendor_id", "vendor_id"),
        Index("ix_jobs_document_id", "document_id"),
    )

    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, native_enum=False, length=32, create_constraint=False, validate_strings=True), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=16, create_constraint=False, validate_strings=True),
        nullable=False,
        default=JobStatus.QUEUED,
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("vendor_documents.id", ondelete="CASCADE"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
