"""sites and devices

Revision ID: 0002_sites_devices
Revises: 0001_initial
Create Date: 2026-05-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_sites_devices"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- sites ---
    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("address", sa.String(512)),
        sa.Column("contact_email", sa.String(254)),
        sa.Column("contact_phone", sa.String(64)),
        sa.Column("notes", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_sites_org_slug"),
    )
    op.create_index("ix_sites_organization_id", "sites", ["organization_id"])
    op.create_index("ix_sites_slug", "sites", ["slug"])

    # --- devices ---
    device_status_enum = sa.Enum("unknown", "online", "offline", "error", name="device_status")
    device_status_enum.create(op.get_bind())

    device_transport_enum = sa.Enum("api", "rest", "ssh", "netconf", name="device_transport")
    device_transport_enum.create(op.get_bind())

    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="8728"),
        sa.Column("transport", device_transport_enum, nullable=False, server_default="api"),
        sa.Column("verify_tls", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_encrypted", sa.String(1024)),
        sa.Column("api_key_encrypted", sa.String(1024)),
        sa.Column("model", sa.String(128)),
        sa.Column("serial", sa.String(128)),
        sa.Column("firmware", sa.String(64)),
        sa.Column("status", device_status_enum, nullable=False, server_default="unknown"),
        sa.Column("status_error", sa.String(1024)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(2048)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_devices_org_name"),
    )
    op.create_index("ix_devices_organization_id", "devices", ["organization_id"])
    op.create_index("ix_devices_site_id", "devices", ["site_id"])
    op.create_index("ix_devices_vendor", "devices", ["vendor"])


def downgrade() -> None:
    op.drop_table("devices")
    sa.Enum(name="device_transport").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="device_status").drop(op.get_bind(), checkfirst=False)
    op.drop_table("sites")
