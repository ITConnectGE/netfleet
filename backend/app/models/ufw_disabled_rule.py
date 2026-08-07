from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin


class UfwDisabledRule(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """A ufw rule an operator switched off.

    ufw has no concept of a disabled rule — a rule is either in the ruleset or
    it is not. So "disabled" means removed from the host and remembered here,
    with enough to put it back where it was.

    That makes this table the one place where NetFleet holds firewall state the
    host does not, and the UI says so out loud rather than in a tooltip:
    somebody reading `ufw status` on the host will not see these, and must not
    be misled by our screen into thinking they exist there.
    """

    __tablename__ = "ufw_disabled_rules"
    __table_args__ = (
        # The spec identifies the rule; disabling the same one twice is a bug,
        # and letting it happen would leave a duplicate to re-enable.
        UniqueConstraint("device_id", "spec", name="uq_ufw_disabled_device_spec"),
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
    disabled_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    # The `ufw show added` line. Everything needed to reinstall the rule, and
    # the same handle the live rules are addressed by.
    spec: Mapped[str] = mapped_column(String(512), nullable=False)
    # Where it sat when it was switched off. A hint, not a promise: the
    # ruleset can change while a rule is disabled, so re-enabling clamps this
    # to what currently exists and reports where the rule actually landed.
    position: Mapped[int | None] = mapped_column(Integer)
    disabled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
