"""Secret-reveal & secret-rotation tracking.

When a user clicks "Reveal" on a device secret (PPP password, WireGuard private
key, preshared key, …) we record an entry here. When the same secret is
subsequently rotated (peer recreated, password changed) we record that too.

The risk report joins these two streams: secrets a user saw which haven't been
rotated since the reveal are flagged as needing rotation when that user leaves
or loses access.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import IdMixin


class SecretKind(StrEnum):
    PPP_PASSWORD = "ppp.password"
    WIREGUARD_PRIVATE_KEY = "wireguard.private_key"
    WIREGUARD_PRESHARED_KEY = "wireguard.preshared_key"
    DEVICE_USER_PASSWORD = "device.user.password"
    OTHER = "other"


class SecretReveal(IdMixin, Base):
    """One row per "I clicked Reveal" — what was viewed, by whom, when."""

    __tablename__ = "secret_reveals"

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    secret_kind: Mapped[SecretKind] = mapped_column(
        Enum(SecretKind, name="secret_kind"), nullable=False, index=True
    )
    # Stable per-device identifier for the secret — e.g. ppp_secret_id, wireguard_peer_id,
    # device_user_name. Used to link reveals to subsequent rotations.
    secret_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    secret_label: Mapped[str | None] = mapped_column(String(255))

    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    justification: Mapped[str | None] = mapped_column(String(1024))


class SecretRotation(IdMixin, Base):
    """One row each time a secret is rotated, by us or detected on the device."""

    __tablename__ = "secret_rotations"

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rotated_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    device_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    secret_kind: Mapped[SecretKind] = mapped_column(
        Enum(SecretKind, name="secret_kind"), nullable=False, index=True
    )
    secret_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(String(512))
