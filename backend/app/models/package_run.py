from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin


class PackageRunKind(StrEnum):
    REFRESH = "refresh"
    UPGRADE = "upgrade"


class PackageRunState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    # The API process restarted while this run was in flight. The command
    # itself may well have completed on the host — we simply stopped being
    # able to observe it, and saying so is better than leaving a row that
    # claims to still be running months later.
    INTERRUPTED = "interrupted"


class PackageRun(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """One package-manager invocation against one host.

    An upgrade can take half an hour, which no HTTP request should hold
    open, so the request starts a background task and returns this row's id
    to poll. Output is kept because when an upgrade fails the last twenty
    lines are the whole diagnosis.
    """

    __tablename__ = "device_package_runs"

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
    # Null when the scheduler started it rather than a person.
    started_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    kind: Mapped[PackageRunKind] = mapped_column(
        Enum(PackageRunKind, name="package_run_kind", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
    )
    state: Mapped[PackageRunState] = mapped_column(
        Enum(PackageRunState, name="package_run_state", values_callable=lambda c: [e.value for e in c]),
        nullable=False,
        default=PackageRunState.RUNNING,
        index=True,
    )
    # Comma-separated; empty means "everything upgradable".
    packages: Mapped[str | None] = mapped_column(String(2048))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    # Capped by the service before it gets here — an upgrade of a stale box
    # can print megabytes and none of the middle is ever read.
    output: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(String(2048))
