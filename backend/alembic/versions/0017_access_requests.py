"""access_requests table + role_assignments.expires_at

Revision ID: 0017_access_requests
Revises: 0016_user_login_otp
Create Date: 2026-06-01

P21 Stage 6 — operators without access to a tenant/site/device file a
request; admins grant or deny. Granted assignments can carry an
expires_at watermark so a "give them access for the maintenance
window" workflow becomes trivial.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_access_requests"
down_revision: str | None = "0016_user_login_otp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reuse the enum from 0003_rbac (assignment_scope). PostgreSQL
    # complains if we recreate it, so we mark it as already existing.
    scope_enum = postgresql.ENUM(
        "organization",
        "tenant",
        "site",
        "device",
        name="assignment_scope",
        create_type=False,
    )
    status_enum = postgresql.ENUM(
        "pending", "approved", "denied", "cancelled",
        name="access_request_status",
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "access_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "requester_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("scope_type", scope_enum, nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            status_enum,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "decided_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # When approved, the admin can copy the chosen expiry onto each
        # assignment AND keep a denormalised copy here so the request
        # log is self-contained.
        sa.Column("granted_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_access_requests_org_status",
        "access_requests",
        ["organization_id", "status"],
    )

    # Side table linking the request to each role assignment it produced.
    op.create_table(
        "access_request_grants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "access_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("access_requests.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "role_assignment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("role_assignments.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )

    # Time-limited role assignments. NULL == permanent (existing behaviour).
    op.add_column(
        "role_assignments",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("role_assignments", "expires_at")
    op.drop_table("access_request_grants")
    op.drop_index("ix_access_requests_org_status", table_name="access_requests")
    op.drop_table("access_requests")
    postgresql.ENUM(name="access_request_status").drop(
        op.get_bind(), checkfirst=True
    )
