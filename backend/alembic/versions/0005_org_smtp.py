"""organization SMTP settings

Revision ID: 0005_org_smtp
Revises: 0004_secret_audit
Create Date: 2026-05-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_org_smtp"
down_revision: str | None = "0004_secret_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("smtp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("organizations", sa.Column("smtp_host", sa.String(255), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
    )
    op.add_column("organizations", sa.Column("smtp_username", sa.String(255), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("smtp_password_encrypted", sa.String(1024), nullable=True),
    )
    op.add_column("organizations", sa.Column("smtp_from_email", sa.String(254), nullable=True))
    op.add_column("organizations", sa.Column("smtp_from_name", sa.String(255), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("smtp_use_tls", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "organizations",
        sa.Column("smtp_use_starttls", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    for col in (
        "smtp_use_starttls",
        "smtp_use_tls",
        "smtp_from_name",
        "smtp_from_email",
        "smtp_password_encrypted",
        "smtp_username",
        "smtp_port",
        "smtp_host",
        "smtp_enabled",
    ):
        op.drop_column("organizations", col)
