from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin


class ChangeGuardState(StrEnum):
    ARMED = "armed"
    # The change was verified reachable and the host-side timer cancelled.
    CONFIRMED = "confirmed"
    # NetFleet restored the snapshot itself, before the timer fired.
    ROLLED_BACK = "rolled_back"
    # The window elapsed with no confirmation, so the host restored itself.
    # NetFleet records this rather than claiming a state it did not observe.
    EXPIRED = "expired"


class ChangeGuard(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """One armed dead-man timer protecting one firewall change.

    The timer itself lives on the managed host, not here — that is the whole
    point. It still fires when the thing that broke is the path between
    NetFleet and the host, or when this API process dies mid-change. This row
    exists so the UI can say "unconfirmed change, 86s left" and so a restart
    does not leave an armed guard nobody knows about.
    """

    __tablename__ = "device_change_guards"

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
    started_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    # Hex, generated here, and the suffix of both the host-side systemd unit
    # and the snapshot directory. Validated before it is ever interpolated
    # into a path — see `_assert_safe_token` in drivers/linux.py.
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Free-form ("ufw.enable", "ufw.rule.add"): a plain string rather than an
    # enum so a new guarded operation does not need a migration to name itself.
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[ChangeGuardState] = mapped_column(
        Enum(
            ChangeGuardState,
            name="change_guard_state",
            values_callable=lambda c: [e.value for e in c],
        ),
        nullable=False,
        default=ChangeGuardState.ARMED,
        index=True,
    )

    snapshot_path: Mapped[str | None] = mapped_column(String(512))
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    armed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What actually happened, in the words the operator will read.
    detail: Mapped[str | None] = mapped_column(String(2048))
