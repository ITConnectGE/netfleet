"""initial schema — organizations, users, refresh_tokens, audit_logs

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("is_setup_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    auth_method_enum = sa.Enum("local", "oidc", name="auth_method")
    auth_method_enum.create(op.get_bind())

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("totp_secret_encrypted", sa.String(512)),
        sa.Column("totp_enrolled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("oidc_sub", sa.String(255)),
        sa.Column("oidc_provider", sa.String(64)),
        sa.Column("auth_method", auth_method_enum, nullable=False, server_default="local"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        sa.UniqueConstraint("oidc_sub", name="uq_users_oidc_sub"),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_oidc_sub", "users", ["oidc_sub"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["refresh_tokens.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])

    audit_outcome_enum = sa.Enum("ok", "denied", "failed", name="audit_outcome")
    audit_outcome_enum.create(op.get_bind())

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True)),
        sa.Column("section", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("outcome", audit_outcome_enum, nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True)),
        sa.Column("site_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("response_meta", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("error_message", sa.String(1024)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_ts", "audit_logs", ["ts"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_section", "audit_logs", ["section"])
    op.create_index("ix_audit_logs_device_id", "audit_logs", ["device_id"])
    op.create_index("ix_audit_logs_site_id", "audit_logs", ["site_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    sa.Enum(name="audit_outcome").drop(op.get_bind(), checkfirst=False)

    op.drop_table("refresh_tokens")
    op.drop_table("users")
    sa.Enum(name="auth_method").drop(op.get_bind(), checkfirst=False)

    op.drop_table("organizations")
