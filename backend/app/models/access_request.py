from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin
from app.models.role import AssignmentScope

if TYPE_CHECKING:
    from app.models.role import RoleAssignment
    from app.models.user import User


class AccessRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"


class AccessRequest(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """A user asking for permission to reach a tenant / site / device.

    Reuses ``AssignmentScope`` for the target so the request flows
    naturally into a RoleAssignment when an admin approves. The
    side-table ``AccessRequestGrant`` records which assignments the
    approval produced so the request log is auditable end-to-end.
    """

    __tablename__ = "access_requests"
    __table_args__ = (
        Index("ix_access_requests_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requester_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_type: Mapped[AssignmentScope] = mapped_column(
        Enum(
            AssignmentScope,
            name="assignment_scope",
            values_callable=lambda c: [e.value for e in c],
            create_type=False,
        ),
        nullable=False,
    )
    scope_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    reason: Mapped[str | None] = mapped_column(Text())
    status: Mapped[AccessRequestStatus] = mapped_column(
        Enum(
            AccessRequestStatus,
            name="access_request_status",
            values_callable=lambda c: [e.value for e in c],
        ),
        nullable=False,
        default=AccessRequestStatus.PENDING,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    granted_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    decision_note: Mapped[str | None] = mapped_column(Text())

    requester: Mapped[User] = relationship(
        "User", foreign_keys=[requester_user_id]
    )
    decided_by: Mapped[User | None] = relationship(
        "User", foreign_keys=[decided_by_user_id]
    )
    grants: Mapped[list[AccessRequestGrant]] = relationship(
        "AccessRequestGrant", back_populates="request", cascade="all, delete-orphan"
    )


class AccessRequestGrant(IdMixin, Base):
    """Join row between an access request and the RoleAssignment it
    spawned at approval time. Lets the UI render "Request #42 produced
    these three assignments" without re-deriving by timestamp."""

    __tablename__ = "access_request_grants"

    access_request_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("access_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_assignment_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("role_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    request: Mapped[AccessRequest] = relationship(
        "AccessRequest", back_populates="grants"
    )
    role_assignment: Mapped[RoleAssignment] = relationship("RoleAssignment")
