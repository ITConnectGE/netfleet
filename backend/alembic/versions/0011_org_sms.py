"""organization SMS gateway settings

Revision ID: 0011_org_sms
Revises: 0010_device_log_events
Create Date: 2026-05-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_org_sms"
down_revision: str | None = "0010_device_log_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "organizations",
        sa.Column("sms_provider", sa.String(32), nullable=False, server_default="custom"),
    )
    op.add_column("organizations", sa.Column("sms_api_url", sa.Text(), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("sms_http_method", sa.String(8), nullable=False, server_default="POST"),
    )
    op.add_column(
        "organizations",
        sa.Column("sms_body_format", sa.String(16), nullable=False, server_default="form"),
    )
    op.add_column("organizations", sa.Column("sms_body_template", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("sms_auth_header_name", sa.String(64), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("sms_auth_header_value_template", sa.String(256), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("sms_api_key_encrypted", sa.String(1024), nullable=True),
    )
    op.add_column("organizations", sa.Column("sms_sender", sa.String(32), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("sms_success_status_min", sa.Integer(), nullable=False, server_default="200"),
    )
    op.add_column(
        "organizations",
        sa.Column("sms_success_status_max", sa.Integer(), nullable=False, server_default="299"),
    )
    op.add_column(
        "organizations",
        sa.Column("sms_success_body_contains", sa.String(128), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("sms_timeout_seconds", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "organizations", sa.Column("sms_last_test_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("organizations", sa.Column("sms_last_test_ok", sa.Boolean(), nullable=True))
    op.add_column(
        "organizations", sa.Column("sms_last_test_message", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    for col in (
        "sms_last_test_message",
        "sms_last_test_ok",
        "sms_last_test_at",
        "sms_timeout_seconds",
        "sms_success_body_contains",
        "sms_success_status_max",
        "sms_success_status_min",
        "sms_sender",
        "sms_api_key_encrypted",
        "sms_auth_header_value_template",
        "sms_auth_header_name",
        "sms_body_template",
        "sms_body_format",
        "sms_http_method",
        "sms_api_url",
        "sms_provider",
        "sms_enabled",
    ):
        op.drop_column("organizations", col)
