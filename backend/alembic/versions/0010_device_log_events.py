"""central device log events table

Revision ID: 0010_device_log_events
Revises: 0009_firmware_upgrade
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_device_log_events"
down_revision: str | None = "0009_firmware_upgrade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_log_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            sa.UUID(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            sa.UUID(),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "site_id",
            sa.UUID(),
            sa.ForeignKey("sites.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("device_time", sa.String(64)),
        sa.Column(
            "severity",
            sa.Enum(
                "critical", "error", "warning", "info",
                name="event_severity",
            ),
            nullable=False,
        ),
        sa.Column("topics", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("polled", "syslog", name="event_source"),
            nullable=False,
            server_default="polled",
        ),
        sa.Column("dedup_key", sa.String(64), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column(
            "acknowledged_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.UniqueConstraint("device_id", "dedup_key", name="uq_device_log_events_dedup"),
    )
    op.create_index(
        "ix_device_log_events_organization_id",
        "device_log_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_device_log_events_device_id",
        "device_log_events",
        ["device_id"],
    )
    op.create_index(
        "ix_device_log_events_tenant_id",
        "device_log_events",
        ["tenant_id"],
    )
    op.create_index(
        "ix_device_log_events_site_id",
        "device_log_events",
        ["site_id"],
    )
    op.create_index(
        "ix_device_log_events_org_observed_desc",
        "device_log_events",
        ["organization_id", "observed_at"],
    )
    op.create_index(
        "ix_device_log_events_unack_severity",
        "device_log_events",
        ["organization_id", "severity"],
        postgresql_where=sa.text("acknowledged_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_device_log_events_unack_severity", table_name="device_log_events")
    op.drop_index("ix_device_log_events_org_observed_desc", table_name="device_log_events")
    op.drop_index("ix_device_log_events_site_id", table_name="device_log_events")
    op.drop_index("ix_device_log_events_tenant_id", table_name="device_log_events")
    op.drop_index("ix_device_log_events_device_id", table_name="device_log_events")
    op.drop_index("ix_device_log_events_organization_id", table_name="device_log_events")
    op.drop_table("device_log_events")
    op.execute("DROP TYPE event_source")
    op.execute("DROP TYPE event_severity")
