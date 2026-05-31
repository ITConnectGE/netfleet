"""Centralised device log events — error/critical/warning lines pulled from
each device's /log buffer by the worker.

This is the syslog-style central inbox. We don't open a UDP listener (MSP
deployments rarely have inbound paths to client sites); instead the worker
walks devices on a schedule and persists severity-filtered lines with a
content-hash dedup key.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import IdMixin


class EventSeverity(StrEnum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class EventSource(StrEnum):
    POLLED = "polled"      # scraped from /log/print
    SYSLOG = "syslog"      # delivered by UDP/TCP syslog (future)


class DeviceLogEvent(IdMixin, Base):
    __tablename__ = "device_log_events"
    __table_args__ = (
        # Dedup: same line from the same device should land once. The hash
        # rolls device_time + topics + message together; see services/events.py.
        UniqueConstraint("device_id", "dedup_key", name="uq_device_log_events_dedup"),
        Index(
            "ix_device_log_events_org_observed_desc",
            "organization_id",
            "observed_at",
        ),
        Index(
            "ix_device_log_events_unack_severity",
            "organization_id",
            "severity",
            postgresql_where="acknowledged_at IS NULL",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised so the central view can filter by tenant/site without joining.
    tenant_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), index=True
    )
    site_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), index=True
    )

    # When NetFleet first observed the line — authoritative timestamp for
    # ordering and retention. RouterOS times are sometimes relative ("3h2m"),
    # so we don't trust them as PK material.
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    device_time: Mapped[str | None] = mapped_column(String(64))

    severity: Mapped[EventSeverity] = mapped_column(
        Enum(EventSeverity, name="event_severity", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
    )
    topics: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    source: Mapped[EventSource] = mapped_column(
        Enum(EventSource, name="event_source", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
        default=EventSource.POLLED,
    )
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)

    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
