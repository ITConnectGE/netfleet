"""device backup history

Revision ID: 0006_device_backups
Revises: 0005_org_smtp
Create Date: 2026-05-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_device_backups"
down_revision: str | None = "0005_org_smtp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    backup_source_enum = sa.Enum(
        "scheduled", "manual", name="backup_source", values_callable=lambda c: [e.value for e in c]
    )
    backup_status_enum = sa.Enum(
        "ok", "failed", name="backup_status", values_callable=lambda c: [e.value for e in c]
    )

    op.create_table(
        "device_backups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source", backup_source_enum, nullable=False),
        sa.Column("status", backup_status_enum, nullable=False),
        sa.Column("backup_filename", sa.String(255)),
        sa.Column("rsc_filename", sa.String(255)),
        sa.Column("backup_size_bytes", sa.BigInteger()),
        sa.Column("rsc_size_bytes", sa.BigInteger()),
        sa.Column("error_message", sa.String(1024)),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_backups_ts", "device_backups", ["ts"])
    op.create_index("ix_device_backups_organization_id", "device_backups", ["organization_id"])
    op.create_index("ix_device_backups_device_id", "device_backups", ["device_id"])


def downgrade() -> None:
    op.drop_table("device_backups")
    sa.Enum(name="backup_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="backup_source").drop(op.get_bind(), checkfirst=False)
