from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import IdMixin


class AuditOutcome(StrEnum):
    OK = "ok"
    DENIED = "denied"
    FAILED = "failed"


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )

    # what
    section: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[AuditOutcome] = mapped_column(
        Enum(AuditOutcome, name="audit_outcome", values_callable=lambda c: [e.value for e in c]), nullable=False
    )

    # where (optional device scope)
    device_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    site_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)

    # context
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    request_payload: Mapped[dict | None] = mapped_column(JSONB)
    response_meta: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(String(1024))
