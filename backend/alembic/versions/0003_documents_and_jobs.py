"""vendor documents and background jobs

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOC_TYPES = ("GST_CERTIFICATE", "BUSINESS_LICENSE", "OTHER")
DOC_STATUSES = ("UPLOADED", "PROCESSING", "PROCESSED", "FAILED")
JOB_TYPES = ("DOCUMENT_PROCESSING",)
JOB_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _enum(values: tuple[str, ...], name: str, length: int) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=length, create_constraint=False)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "vendor_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("document_type", _enum(DOC_TYPES, "documenttype", 32), nullable=False),
        sa.Column("status", _enum(DOC_STATUSES, "documentstatus", 16), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extracted_chars", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_vendor_documents"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], name="fk_vendor_documents_vendor_id_vendors",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], name="fk_vendor_documents_uploaded_by_id_users",
                                ondelete="SET NULL"),
        sa.UniqueConstraint("vendor_id", "sha256", name="uq_vendor_documents_vendor_id_sha256"),
        sa.UniqueConstraint("storage_key", name="uq_vendor_documents_storage_key"),
        sa.CheckConstraint(f"document_type IN ({_in(DOC_TYPES)})", name="ck_vendor_documents_valid_document_type"),
        sa.CheckConstraint(f"status IN ({_in(DOC_STATUSES)})", name="ck_vendor_documents_valid_status"),
    )
    op.create_index("ix_vendor_documents_vendor_id", "vendor_documents", ["vendor_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_type", _enum(JOB_TYPES, "jobtype", 32), nullable=False),
        sa.Column("status", _enum(JOB_STATUSES, "jobstatus", 16), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], name="fk_jobs_vendor_id_vendors", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["vendor_documents.id"], name="fk_jobs_document_id_vendor_documents",
                                ondelete="CASCADE"),
        sa.CheckConstraint(f"job_type IN ({_in(JOB_TYPES)})", name="ck_jobs_valid_job_type"),
        sa.CheckConstraint(f"status IN ({_in(JOB_STATUSES)})", name="ck_jobs_valid_status"),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_vendor_id", "jobs", ["vendor_id"])
    op.create_index("ix_jobs_document_id", "jobs", ["document_id"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("vendor_documents")
