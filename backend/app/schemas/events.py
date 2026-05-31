from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.device_log_event import EventSeverity, EventSource


class EventPublic(BaseModel):
    id: UUID
    organization_id: UUID
    device_id: UUID
    device_name: str | None
    tenant_id: UUID | None
    tenant_name: str | None
    site_id: UUID | None
    site_name: str | None
    observed_at: datetime
    device_time: str | None
    severity: EventSeverity
    topics: str
    message: str
    source: EventSource
    acknowledged_at: datetime | None
    acknowledged_by_user_id: UUID | None
    acknowledged_by_email: str | None


class EventListResponse(BaseModel):
    rows: list[EventPublic]
    total: int
    unacknowledged_total: int
    by_severity: dict[str, int]


class EventAcknowledgeRequest(BaseModel):
    ids: list[UUID]
