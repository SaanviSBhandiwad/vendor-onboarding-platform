import enum
import uuid

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentType(enum.StrEnum):
    GST_CERTIFICATE = "GST_CERTIFICATE"
    BUSINESS_LICENSE = "BUSINESS_LICENSE"
    OTHER = "OTHER"


# Once all of these are uploaded, the application moves to DOCUMENTS_SUBMITTED automatically.
REQUIRED_DOCUMENT_TYPES = frozenset({DocumentType.GST_CERTIFICATE, DocumentType.BUSINESS_LICENSE})


class DocumentStatus(enum.StrEnum):
    UPLOADED = "UPLOADED"      # stored, waiting for a worker
    PROCESSING = "PROCESSING"  # a worker is extracting text
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


def _in(values: type[enum.StrEnum]) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class VendorDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendor_documents"
    __table_args__ = (
        # The same file cannot be uploaded twice for one vendor.
        UniqueConstraint("vendor_id", "sha256", name="uq_vendor_documents_vendor_id_sha256"),
        UniqueConstraint("storage_key", name="uq_vendor_documents_storage_key"),
        CheckConstraint(f"document_type IN ({_in(DocumentType)})", name="valid_document_type"),
        CheckConstraint(f"status IN ({_in(DocumentStatus)})", name="valid_status"),
        Index("ix_vendor_documents_vendor_id", "vendor_id"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, native_enum=False, length=32, create_constraint=False, validate_strings=True),
        nullable=False,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False, length=16, create_constraint=False, validate_strings=True),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)  # detected from file bytes
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_chars: Mapped[int | None] = mapped_column(Integer)
