"""device firmware-upgrade tracking + auto-upgrade policy

Revision ID: 0009_firmware_upgrade
Revises: 0008_tenants
Create Date: 2026-05-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_firmware_upgrade"
down_revision: str | None = "0008_tenants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "auto_upgrade_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("devices", sa.Column("auto_upgrade_window_start_hour", sa.Integer()))
    op.add_column("devices", sa.Column("auto_upgrade_window_end_hour", sa.Integer()))
    op.add_column(
        "devices",
        sa.Column("last_upgrade_triggered_at", sa.DateTime(timezone=True)),
    )
    op.add_column("devices", sa.Column("last_upgrade_status", sa.String(32)))
    op.add_column("devices", sa.Column("last_upgrade_error", sa.String(2048)))
    op.add_column("devices", sa.Column("last_upgrade_from_version", sa.String(64)))
    op.add_column("devices", sa.Column("last_upgrade_to_version", sa.String(64)))


def downgrade() -> None:
    op.drop_column("devices", "last_upgrade_to_version")
    op.drop_column("devices", "last_upgrade_from_version")
    op.drop_column("devices", "last_upgrade_error")
    op.drop_column("devices", "last_upgrade_status")
    op.drop_column("devices", "last_upgrade_triggered_at")
    op.drop_column("devices", "auto_upgrade_window_end_hour")
    op.drop_column("devices", "auto_upgrade_window_start_hour")
    op.drop_column("devices", "auto_upgrade_enabled")
