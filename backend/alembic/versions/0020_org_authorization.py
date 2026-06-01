"""organization authorization settings (Microsoft / Google OIDC + MFA toggles)

Revision ID: 0020_org_authorization
Revises: 0019_device_ssh_port
Create Date: 2026-06-01

Adds per-org Microsoft Entra and Google OIDC client config plus global
toggles for the three MFA factors (TOTP app, SMS OTP, email OTP) so the
org admin can switch them on/off from Settings → Authorization without
touching env vars.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_org_authorization"
down_revision: str | None = "0019_device_ssh_port"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_BOOL_TRUE = sa.true()
_BOOL_FALSE = sa.false()


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("microsoft_oidc_enabled", sa.Boolean(), nullable=False, server_default=_BOOL_FALSE),
    )
    op.add_column(
        "organizations",
        sa.Column("microsoft_oidc_tenant_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("microsoft_oidc_client_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("microsoft_oidc_client_secret_encrypted", sa.String(1024), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("google_oidc_enabled", sa.Boolean(), nullable=False, server_default=_BOOL_FALSE),
    )
    op.add_column(
        "organizations",
        sa.Column("google_oidc_client_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("google_oidc_client_secret_encrypted", sa.String(1024), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("mfa_totp_enabled", sa.Boolean(), nullable=False, server_default=_BOOL_TRUE),
    )
    op.add_column(
        "organizations",
        sa.Column("mfa_sms_otp_enabled", sa.Boolean(), nullable=False, server_default=_BOOL_TRUE),
    )
    op.add_column(
        "organizations",
        sa.Column("mfa_email_otp_enabled", sa.Boolean(), nullable=False, server_default=_BOOL_TRUE),
    )


def downgrade() -> None:
    for col in (
        "mfa_email_otp_enabled",
        "mfa_sms_otp_enabled",
        "mfa_totp_enabled",
        "google_oidc_client_secret_encrypted",
        "google_oidc_client_id",
        "google_oidc_enabled",
        "microsoft_oidc_client_secret_encrypted",
        "microsoft_oidc_client_id",
        "microsoft_oidc_tenant_id",
        "microsoft_oidc_enabled",
    ):
        op.drop_column("organizations", col)
