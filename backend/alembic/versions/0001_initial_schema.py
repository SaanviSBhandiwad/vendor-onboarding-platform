"""initial schema: vendors and audit_logs

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ("PENDING", "DOCUMENTS_SUBMITTED", "UNDER_REVIEW", "MANUAL_REVIEW", "APPROVED", "REJECTED")


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=False),
        sa.Column("contact_phone", sa.String(20), nullable=True),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("service_type", sa.String(64), nullable=False),
        sa.Column("status", sa.Enum(*STATUSES, name="vendorstatus", native_enum=False,
                                    length=32, create_constraint=False), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_vendors"),
        sa.UniqueConstraint("email", name="uq_vendors_email"),
        sa.UniqueConstraint("gstin", name="uq_vendors_gstin"),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")",
            name="ck_vendors_valid_status",
        ),
    )
    op.create_index("ix_vendors_status", "vendors", ["status"])
    op.create_index("ix_vendors_region", "vendors", ["region"])
    op.create_index("ix_vendors_created_at", "vendors", ["created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_vendors_created_at", table_name="vendors")
    op.drop_index("ix_vendors_region", table_name="vendors")
    op.drop_index("ix_vendors_status", table_name="vendors")
    op.drop_table("vendors")
