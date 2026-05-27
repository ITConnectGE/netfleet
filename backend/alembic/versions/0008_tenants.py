"""tenants layer above sites + TENANT assignment scope

Revision ID: 0008_tenants
Revises: 0007_device_firmware
Create Date: 2026-05-27

The migration is non-destructive: every existing site is parented to a
freshly-created 'Default' tenant for its organization, then sites.tenant_id
is made NOT NULL. Existing role assignments are untouched (no new TENANT
scope rows are added; only the enum value is added so it's available going
forward).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_tenants"
down_revision: str | None = "0007_device_firmware"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. Create tenants table ----------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("description", sa.String(1024)),
        sa.Column("primary_contact_name", sa.String(255)),
        sa.Column("primary_contact_email", sa.String(254)),
        sa.Column("primary_contact_phone", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_tenants_org_slug"),
    )
    op.create_index("ix_tenants_organization_id", "tenants", ["organization_id"])
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # --- 2. Add tenant_id (nullable for now, will backfill) -------------
    op.add_column(
        "sites",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # --- 3. Backfill: 'Default' tenant per org, link existing sites -----
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            INSERT INTO tenants (id, organization_id, name, slug, description)
            SELECT
                gen_random_uuid(),
                o.id,
                'Default',
                'default',
                'Auto-created during upgrade to v0.9 — your existing sites were '
                  || 'moved here. Rename or split into more tenants any time.'
            FROM organizations o
            WHERE NOT EXISTS (
                SELECT 1 FROM tenants t
                WHERE t.organization_id = o.id AND t.slug = 'default'
            )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE sites s
               SET tenant_id = t.id
              FROM tenants t
             WHERE t.organization_id = s.organization_id
               AND t.slug = 'default'
               AND s.tenant_id IS NULL
            """
        )
    )

    # --- 4. Lock tenant_id NOT NULL + FK index --------------------------
    op.alter_column("sites", "tenant_id", nullable=False)
    op.create_foreign_key(
        "fk_sites_tenant",
        "sites",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_sites_tenant_id", "sites", ["tenant_id"])

    # --- 5. Extend assignment_scope enum with 'tenant' ------------------
    op.execute("ALTER TYPE assignment_scope ADD VALUE IF NOT EXISTS 'tenant'")


def downgrade() -> None:
    # We CANNOT drop a value from an enum in Postgres without a full type
    # rebuild — leave 'tenant' in the enum on rollback; it's a no-op for
    # the app since no rows would still reference it after sites are
    # detached.
    op.drop_index("ix_sites_tenant_id", table_name="sites")
    op.drop_constraint("fk_sites_tenant", "sites", type_="foreignkey")
    op.drop_column("sites", "tenant_id")
    op.drop_table("tenants")
