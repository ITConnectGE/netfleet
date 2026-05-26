"""device firmware-check columns

Revision ID: 0007_device_firmware
Revises: 0006_device_backups
Create Date: 2026-05-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_device_firmware"
down_revision: str | None = "0006_device_backups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("firmware_available", sa.String(64)))
    op.add_column("devices", sa.Column("firmware_channel", sa.String(32)))
    op.add_column("devices", sa.Column("firmware_checked_at", sa.DateTime(timezone=True)))
    op.add_column("devices", sa.Column("routerboard_current", sa.String(64)))
    op.add_column("devices", sa.Column("routerboard_available", sa.String(64)))


def downgrade() -> None:
    op.drop_column("devices", "routerboard_available")
    op.drop_column("devices", "routerboard_current")
    op.drop_column("devices", "firmware_checked_at")
    op.drop_column("devices", "firmware_channel")
    op.drop_column("devices", "firmware_available")
