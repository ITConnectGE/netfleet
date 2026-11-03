"""event_cleared_at — admin "Clear all" on the event inbox

Revision ID: 0027_event_cleared_at
Revises: 0026_ufw_disabled_rules
Create Date: 2026-11-03

Clearing hides events rather than deleting them. The rows' dedup keys are
what keep the next scan from re-importing lines still in a router's log
buffer, so they stay until retention removes them.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_event_cleared_at"
down_revision: str | None = "0026_ufw_disabled_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "device_log_events",
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("device_log_events", "cleared_at")
