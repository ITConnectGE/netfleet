from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    SSH = "ssh"          # Linux hosts, and vendors without an API
    NETCONF = "netconf"  # future — Cisco / Juniper


class DeviceClass(StrEnum):
    """Network gear vs. servers. Both live in `devices` and share the
    tenant/site tree, RBAC scoping and audit log; they differ only in
    which UI pages and driver capabilities apply."""

    NETWORK = "network"
    SERVER = "server"


class OsFamily(StrEnum):
    """Known values for `Device.os_family`. Stored as a plain string, not
    a DB enum — it is discovered data and every new distro would
    otherwise cost a migration."""

    DEBIAN = "debian"      # Debian, Ubuntu, Mint
    RHEL = "rhel"          # RHEL, Rocky, Alma, CentOS, Fedora
    ALPINE = "alpine"
    SUSE = "suse"
    UNKNOWN = "unknown"


class BecomeMethod(StrEnum):
    """How the driver escalates privilege after logging in."""

    NONE = "none"   # already root, or the command needs no escalation
    SUDO = "sudo"


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
    device_class: Mapped[DeviceClass] = mapped_column(
        Enum(DeviceClass, name="device_class", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
        default=DeviceClass.NETWORK,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=8728)
    # Independent of `port` so operators that moved RouterOS SSH off 22
    # can still take backups — binary .backup files are SFTP-pulled
    # off the device, librouteros has no file-download method.
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
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

    # SSH key auth (Linux hosts). NetFleet generates the pair itself during
    # onboarding; the public half goes into the onboarding script and only
    # the private half is stored here.
    ssh_private_key_encrypted: Mapped[str | None] = mapped_column(Text)
    ssh_key_passphrase_encrypted: Mapped[str | None] = mapped_column(String(1024))
    become_method: Mapped[BecomeMethod] = mapped_column(
        Enum(
            BecomeMethod,
            name="device_become_method",
            values_callable=lambda c: [e.value for e in c],
        ),
        nullable=False,
        default=BecomeMethod.NONE,
    )
    become_password_encrypted: Mapped[str | None] = mapped_column(String(1024))
    # Trust-on-first-use: pinned on the first successful connect. A later
    # mismatch fails the connection rather than silently accepting a new key.
    ssh_host_key_fingerprint: Mapped[str | None] = mapped_column(String(128))

    # discovered metadata (populated on first successful connection)
    model: Mapped[str | None] = mapped_column(String(128))
    serial: Mapped[str | None] = mapped_column(String(128))
    firmware: Mapped[str | None] = mapped_column(String(64))
    os_family: Mapped[str | None] = mapped_column(String(32))
    os_version: Mapped[str | None] = mapped_column(String(64))

    # runtime status — updated by worker poller and test-connection calls
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, name="device_status", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
        default=DeviceStatus.UNKNOWN,
    )
    status_error: Mapped[str | None] = mapped_column(String(1024))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Firmware-update tracking (refreshed nightly by the scheduler)
    firmware_available: Mapped[str | None] = mapped_column(String(64))
    firmware_channel: Mapped[str | None] = mapped_column(String(32))
    firmware_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    routerboard_current: Mapped[str | None] = mapped_column(String(64))
    routerboard_available: Mapped[str | None] = mapped_column(String(64))

    # Auto-upgrade policy + last attempt outcome
    auto_upgrade_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_upgrade_window_start_hour: Mapped[int | None] = mapped_column(Integer)
    auto_upgrade_window_end_hour: Mapped[int | None] = mapped_column(Integer)
    last_upgrade_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_upgrade_status: Mapped[str | None] = mapped_column(String(32))
    last_upgrade_error: Mapped[str | None] = mapped_column(String(2048))
    last_upgrade_from_version: Mapped[str | None] = mapped_column(String(64))
    last_upgrade_to_version: Mapped[str | None] = mapped_column(String(64))

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(String(2048))

    organization: Mapped[Organization] = relationship("Organization")
    site: Mapped[Site] = relationship("Site", back_populates="devices")
