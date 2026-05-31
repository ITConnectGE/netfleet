"""user password lifecycle: must_change_password

Revision ID: 0015_user_password_lifecycle
Revises: 0014_user_profile
Create Date: 2026-05-31

P21 Stage 3 — when an invite uses an auto-generated password (the new
default) we want the recipient forced through a password change before
they can do anything else. The flag is also set when an admin resets
someone's password from the Users page.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_user_password_lifecycle"
down_revision: str | None = "0014_user_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Drop the default so future inserts go through the model layer
    # explicitly (matches the pattern used for is_active/is_admin).
    op.alter_column("users", "must_change_password", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
