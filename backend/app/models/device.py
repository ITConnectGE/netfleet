from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.site import Site


class DeviceStatus(StrEnum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


class DeviceTransport(StrEnum):
    API = "api"          # native RouterOS API (8728/8729)
    REST = "rest"        # RouterOS 7.x REST over HTTPS
    SSH = "ssh"          # future — for vendors without an API
    NETCONF = "netconf"  # future — Cisco / Juniper


class Device(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """A network device managed by NetFleet — vendor identified by `vendor` (matches driver registry key)."""

    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_devices_org_name"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    vendor: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=8728)
    transport: Mapped[DeviceTransport] = mapped_column(
        Enum(DeviceTransport, name="device_transport", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
        default=DeviceTransport.API,
    )
    verify_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # credentials — encrypted at rest via Fernet
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_encrypted: Mapped[str | None] = mapped_column(String(1024))
    api_key_encrypted: Mapped[str | None] = mapped_column(String(1024))

    # discovered metadata (populated on first successful connection)
    model: Mapped[str | None] = mapped_column(String(128))
    serial: Mapped[str | None] = mapped_column(String(128))
    firmware: Mapped[str | None] = mapped_column(String(64))

    # runtime status — updated by worker poller and test-connection calls
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, name="device_status", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
        default=DeviceStatus.UNKNOWN,
    )
    status_error: Mapped[str | None] = mapped_column(String(1024))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(String(2048))

    organization: Mapped[Organization] = relationship("Organization")
    site: Mapped[Site] = relationship("Site", back_populates="devices")
