"""host_metric_samples — NetFleet API host's own resource snapshots

Revision ID: 0021_host_metric_samples
Revises: 0020_org_authorization
Create Date: 2026-06-03

One row per host_metric scheduler tick (~60 s). The scheduler caps the
table at NETFLEET_HOST_METRIC_MAX_ROWS so disk pressure stays bounded
regardless of how long the deployment has been running — operators
reason about "we hold ≈ 5 MB of history", not "we hold 30 days".
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0021_host_metric_samples"
down_revision: str | None = "0020_org_authorization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "host_metric_samples",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sampled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("cpu_percent", sa.Float(), nullable=False),
        sa.Column("cpu_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memory_used_bytes", sa.BigInteger(), nullable=False),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("disk_used_bytes", sa.BigInteger(), nullable=False),
        sa.Column("disk_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("net_rx_bytes", sa.BigInteger(), nullable=False),
        sa.Column("net_tx_bytes", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_host_metric_samples_sampled_at",
        "host_metric_samples",
        ["sampled_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_host_metric_samples_sampled_at",
        table_name="host_metric_samples",
    )
    op.drop_table("host_metric_samples")
