"""wireguard peer secret cache (preshared keys)

Revision ID: 0018_wg_peer_secrets
Revises: 0017_access_requests
Create Date: 2026-06-01

P21 Stage 9 — RouterOS 7.x masks the preshared-key field in
/interface/wireguard/peers/print, so the driver can't fetch it back
once the peer was created. We cache it (encrypted) on NetFleet's side
at creation time, then prefer the cached value when generating client
configs.

Existing peers without a cached PSK keep working — the client config
just omits the PresharedKey line, exactly like before.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_wg_peer_secrets"
down_revision: str | None = "0017_access_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wg_peer_secrets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Router-side peer ID (e.g. "*4" on MikroTik) — opaque to NetFleet.
        sa.Column("router_peer_id", sa.String(64), nullable=False),
        sa.Column("preshared_key_encrypted", sa.String(512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "device_id", "router_peer_id", name="uq_wg_peer_secrets_device_peer"
        ),
    )


def downgrade() -> None:
    op.drop_table("wg_peer_secrets")
