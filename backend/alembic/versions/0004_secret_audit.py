"""secret reveal and rotation tracking

Revision ID: 0004_secret_audit
Revises: 0003_rbac
Create Date: 2026-05-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_secret_audit"
down_revision: str | None = "0003_rbac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    secret_kind_enum = sa.Enum(
        "ppp.password",
        "wireguard.private_key",
        "wireguard.preshared_key",
        "device.user.password",
        "other",
        name="secret_kind",
    )
    op.create_table(
        "secret_reveals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_kind", secret_kind_enum, nullable=False),
        sa.Column("secret_identifier", sa.String(255), nullable=False),
        sa.Column("secret_label", sa.String(255)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("justification", sa.String(1024)),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_secret_reveals_ts", "secret_reveals", ["ts"])
    op.create_index("ix_secret_reveals_organization_id", "secret_reveals", ["organization_id"])
    op.create_index("ix_secret_reveals_user_id", "secret_reveals", ["user_id"])
    op.create_index("ix_secret_reveals_device_id", "secret_reveals", ["device_id"])
    op.create_index("ix_secret_reveals_secret_kind", "secret_reveals", ["secret_kind"])
    op.create_index("ix_secret_reveals_secret_identifier", "secret_reveals", ["secret_identifier"])

    op.create_table(
        "secret_rotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rotated_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_kind", secret_kind_enum, nullable=False),
        sa.Column("secret_identifier", sa.String(255), nullable=False),
        sa.Column("note", sa.String(512)),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rotated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_secret_rotations_ts", "secret_rotations", ["ts"])
    op.create_index("ix_secret_rotations_organization_id", "secret_rotations", ["organization_id"])
    op.create_index("ix_secret_rotations_device_id", "secret_rotations", ["device_id"])
    op.create_index("ix_secret_rotations_secret_kind", "secret_rotations", ["secret_kind"])
    op.create_index("ix_secret_rotations_secret_identifier", "secret_rotations", ["secret_identifier"])


def downgrade() -> None:
    op.drop_table("secret_rotations")
    op.drop_table("secret_reveals")
    sa.Enum(name="secret_kind").drop(op.get_bind(), checkfirst=False)
