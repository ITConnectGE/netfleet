"""device_change_guards — dead-man timers protecting firewall changes

Revision ID: 0025_change_guards
Revises: 0024_device_package_counts
Create Date: 2026-08-07

A firewall change can sever the connection NetFleet manages the host over,
and the command that does it reports success first: ufw accepts
ESTABLISHED,RELATED before anything else, so the session that applied the
change survives and only the *next* connection fails.

The recovery timer therefore lives on the managed host, where it still
fires when the path between NetFleet and the host is what broke. This table
is NetFleet's record of the ones currently armed, so the UI can show a
pending change and a restart does not leave a guard nobody knows about.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025_change_guards"
down_revision: str | None = "0024_device_package_counts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    state = postgresql.ENUM(
        "armed",
        "confirmed",
        "rolled_back",
        "expired",
        name="change_guard_state",
    )
    state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "device_change_guards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            postgresql.ENUM(name="change_guard_state", create_type=False),
            nullable=False,
            server_default="armed",
        ),
        sa.Column("snapshot_path", sa.String(length=512), nullable=True),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("armed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.String(length=2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_device_change_guards_organization_id",
        "device_change_guards",
        ["organization_id"],
    )
    op.create_index(
        "ix_device_change_guards_device_id", "device_change_guards", ["device_id"]
    )
    op.create_index("ix_device_change_guards_state", "device_change_guards", ["state"])
    # Unique: the token names a systemd unit and a directory on the host, and
    # two guards sharing one would cancel each other's timer.
    op.create_index(
        "uq_device_change_guards_token", "device_change_guards", ["token"], unique=True
    )
    op.alter_column("device_change_guards", "state", server_default=None)


def downgrade() -> None:
    op.drop_index("uq_device_change_guards_token", table_name="device_change_guards")
    op.drop_index("ix_device_change_guards_state", table_name="device_change_guards")
    op.drop_index("ix_device_change_guards_device_id", table_name="device_change_guards")
    op.drop_index(
        "ix_device_change_guards_organization_id", table_name="device_change_guards"
    )
    op.drop_table("device_change_guards")
    postgresql.ENUM(name="change_guard_state").drop(op.get_bind(), checkfirst=False)
