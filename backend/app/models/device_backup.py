"""Device backup history — one row per backup attempt (success or failure).

The actual backup blob lives on the host filesystem under
/opt/netfleet/data/backups/devices/{device_id}/, not in the DB.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import IdMixin


class BackupSource(StrEnum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class BackupStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class DeviceBackup(IdMixin, Base):
    __tablename__ = "device_backups"

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
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

    triggered_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    source: Mapped[BackupSource] = mapped_column(
        Enum(BackupSource, name="backup_source", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
    )
    status: Mapped[BackupStatus] = mapped_column(
        Enum(BackupStatus, name="backup_status", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
    )

    # Filenames relative to /opt/netfleet/data/backups/devices/{device_id}/
    backup_filename: Mapped[str | None] = mapped_column(String(255))
    rsc_filename: Mapped[str | None] = mapped_column(String(255))
    backup_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    rsc_size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    error_message: Mapped[str | None] = mapped_column(String(1024))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
