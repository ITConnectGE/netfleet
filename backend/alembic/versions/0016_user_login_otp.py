"""user login OTP: per-user opt-in + transient code storage

Revision ID: 0016_user_login_otp
Revises: 0015_user_password_lifecycle
Create Date: 2026-05-31

P21 Stage 4 — adds a one-time-code login step.

When ``otp_login_enabled`` is True and the user does NOT have TOTP
enrolled, login generates a 6-digit code, hashes it into
``otp_code_hash`` with a short ``otp_expires_at`` TTL, and ships it via
SMS (when the user has a mobile number set and the org's SMS gateway
is configured) or email otherwise. The client posts the code back to
/auth/otp/verify with the mfa_temp_token to complete the login.

Code is kept on the user row instead of a separate ``login_otps``
table because there is at most one active code per user at a time —
each new login wipes the previous code, which is exactly the upsert a
single row gives us for free.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_user_login_otp"
down_revision: str | None = "0015_user_password_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "otp_login_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.alter_column("users", "otp_login_enabled", server_default=None)
    op.add_column("users", sa.Column("otp_code_hash", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "otp_attempts",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.alter_column("users", "otp_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "otp_attempts")
    op.drop_column("users", "otp_expires_at")
    op.drop_column("users", "otp_code_hash")
    op.drop_column("users", "otp_login_enabled")
