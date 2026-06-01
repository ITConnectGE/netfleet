"""device.ssh_port — separate from the API port

Revision ID: 0019_device_ssh_port
Revises: 0018_wg_peer_secrets
Create Date: 2026-06-01

Backups + restores SFTP-pull files off the device over SSH. The SSH
port is independent of the API port (8728 / 8729) we already store, so
operators that move SSH off 22 used to have their backups silently time
out. Default keeps the existing behaviour (port 22).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_device_ssh_port"
down_revision: str | None = "0018_wg_peer_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "ssh_port",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("22"),
        ),
    )
    op.alter_column("devices", "ssh_port", server_default=None)


def downgrade() -> None:
    op.drop_column("devices", "ssh_port")
