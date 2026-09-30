"""users table, roles, and vendor ownership

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("VENDOR", "OPERATIONS", "ADMIN")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum(*ROLES, name="userrole", native_enum=False, length=16,
                                  create_constraint=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN (" + ", ".join(f"'{r}'" for r in ROLES) + ")", name="ck_users_valid_role"),
    )

    # Existing vendors keep owner_id = NULL; they remain visible to staff.
    with op.batch_alter_table("vendors") as batch:
        batch.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_vendors_owner_id_users", "users", ["owner_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_unique_constraint("uq_vendors_owner_id", ["owner_id"])


def downgrade() -> None:
    with op.batch_alter_table("vendors") as batch:
        batch.drop_constraint("uq_vendors_owner_id", type_="unique")
        batch.drop_constraint("fk_vendors_owner_id_users", type_="foreignkey")
        batch.drop_column("owner_id")
    op.drop_table("users")
