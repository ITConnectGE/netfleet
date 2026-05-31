"""user profile fields: mobile phone + notifications_seen_at

Revision ID: 0014_user_profile
Revises: 0013_site_geolocation
Create Date: 2026-05-31

P21 Stage 2 — profile / notifications. Mobile phone supports the
upcoming SMS-OTP login (#17) and SMS-based invite (#15.2); the
notifications_seen_at watermark drives the navbar bell (#20).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_user_profile"
down_revision: str | None = "0013_site_geolocation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mobile_phone", sa.String(32), nullable=True))
    op.add_column(
        "users",
        sa.Column("notifications_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "notifications_seen_at")
    op.drop_column("users", "mobile_phone")
