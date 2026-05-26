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
    section: str
    action: str
    outcome: AuditOutcome
    device_id: UUID | None
    site_id: UUID | None
    ip_address: str | None
    user_agent: str | None
    request_payload: dict[str, Any] | None
    response_meta: dict[str, Any] | None
    error_message: str | None

    model_config = {"from_attributes": True}


class AuditPage(BaseModel):
    items: list[AuditLogEntry]
    total: int
    limit: int
    offset: int
