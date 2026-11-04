from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.audit_log import AuditOutcome


class AuditLogEntry(BaseModel):
    id: UUID
    ts: datetime
    user_id: UUID | None
    user_email: str | None
    user_name: str | None = None
    section: str
    action: str
    outcome: AuditOutcome
    device_id: UUID | None
    device_name: str | None = None
    site_id: UUID | None
    site_name: str | None = None
    ip_address: str | None
    user_agent: str | None
    request_payload: dict[str, Any] | None
    response_meta: dict[str, Any] | None
    error_message: str | None
    session_id: UUID | None = None

    model_config = {"from_attributes": True}


class AuditPage(BaseModel):
    items: list[AuditLogEntry]
    total: int
    limit: int
    offset: int
    # Sessions on this page that are still signed in.
    active_session_ids: list[UUID] = []


class AuditSessionDetail(BaseModel):
    session_id: UUID
    user_id: UUID | None
    user_email: str | None
    user_name: str | None
    role: str | None
    started_at: datetime | None
    last_activity_at: datetime | None
    sign_in_method: str | None
    ip_address: str | None
    user_agent: str | None
    active: bool
    expires_at: datetime | None
    previous_session_id: UUID | None
    next_session_id: UUID | None
    entries: list[AuditLogEntry]
