from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import IdMixin

if TYPE_CHECKING:
    pass


class WgPeerSecret(IdMixin, Base):
    """NetFleet-side cache of a WireGuard peer's PSK.

    RouterOS 7.x returns the preshared-key field masked as ``********``
    in /interface/wireguard/peers/print, so the driver can't read the
    plaintext back after creation. We persist it (Fernet-encrypted) at
    create time so a later client-config regeneration sees the real
    value instead of masking the operator's only copy.
    """

    __tablename__ = "wg_peer_secrets"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "router_peer_id", name="uq_wg_peer_secrets_device_peer"
        ),
    )

    device_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    router_peer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    preshared_key_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
