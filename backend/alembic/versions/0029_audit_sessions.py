"""audit_sessions — tie audit rows and refresh tokens to a sign-in session

Revision ID: 0029_audit_sessions
Revises: 0028_totp_guards
Create Date: 2026-11-04

A login mints a session id that every rotated refresh token inherits and
every access token carries as `sid`. Audit rows record it, so the audit
log can be grouped by session and one session viewed on its own.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0029_audit_sessions"
down_revision: str | None = "0028_totp_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("session_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"])
    op.add_column("audit_logs", sa.Column("session_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_audit_logs_session_id", "audit_logs", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_session_id", table_name="audit_logs")
    op.drop_column("audit_logs", "session_id")
    op.drop_index("ix_refresh_tokens_session_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "session_id")
