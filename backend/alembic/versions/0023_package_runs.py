"""device_package_runs — track long package-manager operations

Revision ID: 0023_package_runs
Revises: 0022_linux_hosts
Create Date: 2026-07-31

`apt-get upgrade` on a neglected host runs for half an hour. That cannot
be an HTTP request, so the endpoint starts a background task and hands
back a row id to poll. The output is stored because when an upgrade fails
the tail of it is the entire diagnosis, and nobody wants to re-run a
failed upgrade just to read the error again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023_package_runs"
down_revision: str | None = "0022_linux_hosts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    kind = postgresql.ENUM("refresh", "upgrade", name="package_run_kind")
    kind.create(op.get_bind(), checkfirst=True)
    state = postgresql.ENUM(
        "running", "succeeded", "failed", "interrupted", name="package_run_state"
    )
    state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "device_package_runs",
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
        sa.Column(
            "kind",
            postgresql.ENUM(name="package_run_kind", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "state",
            postgresql.ENUM(name="package_run_state", create_type=False),
            nullable=False,
            server_default="running",
        ),
        sa.Column("packages", sa.String(length=2048), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error", sa.String(length=2048), nullable=True),
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
        "ix_device_package_runs_organization_id", "device_package_runs", ["organization_id"]
    )
    op.create_index("ix_device_package_runs_device_id", "device_package_runs", ["device_id"])
    op.create_index("ix_device_package_runs_state", "device_package_runs", ["state"])
    op.alter_column("device_package_runs", "state", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_device_package_runs_state", table_name="device_package_runs")
    op.drop_index("ix_device_package_runs_device_id", table_name="device_package_runs")
    op.drop_index(
        "ix_device_package_runs_organization_id", table_name="device_package_runs"
    )
    op.drop_table("device_package_runs")
    postgresql.ENUM(name="package_run_state").drop(op.get_bind(), checkfirst=False)
    postgresql.ENUM(name="package_run_kind").drop(op.get_bind(), checkfirst=False)
