"""totp_guards — failed-attempt lockout and replay guard for login TOTP

Revision ID: 0028_totp_guards
Revises: 0027_event_cleared_at
Create Date: 2026-11-03

The login TOTP step had no attempt limit, so a known password plus a loop
over the 10^6 code space was an account takeover. Five wrong codes now lock
TOTP login for 15 minutes, and the time step of the last accepted code is
kept so the same code cannot be used twice.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_totp_guards"
down_revision: str | None = "0027_event_cleared_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "totp_failed_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "users", sa.Column("totp_locked_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("totp_last_step", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "totp_last_step")
    op.drop_column("users", "totp_locked_until")
    op.drop_column("users", "totp_failed_attempts")
