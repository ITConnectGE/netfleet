"""ufw_disabled_rules — rules switched off in NetFleet

Revision ID: 0026_ufw_disabled_rules
Revises: 0025_change_guards
Create Date: 2026-08-08

ufw has no disabled state: a rule is in the ruleset or it is not. So a rule
an operator switches off is removed from the host and remembered here, with
its specification and the position it held.

This is the one place NetFleet holds firewall state the host does not, which
is why the UI states it plainly — `ufw status` on the host will not show
these, and anyone reading the host directly must not be misled.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026_ufw_disabled_rules"
down_revision: str | None = "0025_change_guards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ufw_disabled_rules",
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
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "disabled_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("spec", sa.String(length=512), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=False),
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
    )
    op.create_index(
        "ix_ufw_disabled_rules_organization_id",
        "ufw_disabled_rules",
        ["organization_id"],
    )
    op.create_index(
        "ix_ufw_disabled_rules_device_id", "ufw_disabled_rules", ["device_id"]
    )
    # Disabling the same rule twice would leave a duplicate to re-enable.
    op.create_unique_constraint(
        "uq_ufw_disabled_device_spec", "ufw_disabled_rules", ["device_id", "spec"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ufw_disabled_device_spec", "ufw_disabled_rules", type_="unique"
    )
    op.drop_index("ix_ufw_disabled_rules_device_id", table_name="ufw_disabled_rules")
    op.drop_index(
        "ix_ufw_disabled_rules_organization_id", table_name="ufw_disabled_rules"
    )
    op.drop_table("ufw_disabled_rules")
