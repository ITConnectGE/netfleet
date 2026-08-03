"""devices.packages_* — cached package counts for the fleet overview

Revision ID: 0024_device_package_counts
Revises: 0023_package_runs
Create Date: 2026-08-03

A page that lists every server with its pending updates cannot read them
live: that is one SSH session per host on every page load, and forty of
those take minutes. The counts are refreshed by the nightly scheduler and
whenever someone opens a host's Packages tab, exactly as
`firmware_available` already works for RouterOS.

`packages_checked_at` is what makes the numbers honest — a count with no
timestamp is indistinguishable from a count that has been wrong for a
month.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024_device_package_counts"
down_revision: str | None = "0023_package_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("packages_manager", sa.String(length=16)))
    op.add_column("devices", sa.Column("packages_updates_count", sa.Integer()))
    op.add_column("devices", sa.Column("packages_security_count", sa.Integer()))
    op.add_column(
        "devices",
        sa.Column("packages_reboot_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "devices", sa.Column("packages_checked_at", sa.DateTime(timezone=True))
    )
    op.add_column("devices", sa.Column("packages_check_error", sa.String(length=1024)))
    op.alter_column("devices", "packages_reboot_required", server_default=None)


def downgrade() -> None:
    op.drop_column("devices", "packages_check_error")
    op.drop_column("devices", "packages_checked_at")
    op.drop_column("devices", "packages_reboot_required")
    op.drop_column("devices", "packages_security_count")
    op.drop_column("devices", "packages_updates_count")
    op.drop_column("devices", "packages_manager")
