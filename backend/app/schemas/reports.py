from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.audit_log import AuditOutcome
from app.models.secret_audit import SecretKind


class UserActivityRow(BaseModel):
    ts: datetime
    user_id: UUID | None
    user_email: str | None
    section: str
    action: str
    outcome: AuditOutcome
    device_id: UUID | None
    device_name: str | None
    site_id: UUID | None
    site_name: str | None
    tenant_name: str | None
    ip_address: str | None


class UserActivitySummary(BaseModel):
    user_id: UUID | None
    user_email: str | None
    total: int
    writes: int
    failures: int
    sections_touched: int
    devices_touched: int


class UserActivityReport(BaseModel):
    range_from: datetime
    range_to: datetime
    rows: list[UserActivityRow]
    summary: list[UserActivitySummary]
    truncated: bool


class DeviceActivityRow(BaseModel):
    ts: datetime
    user_email: str | None
    section: str
    action: str
    outcome: AuditOutcome
    ip_address: str | None
    request_payload: dict[str, Any] | None
    error_message: str | None


class DeviceActivityReport(BaseModel):
    device_id: UUID
    device_name: str | None
    range_from: datetime
    range_to: datetime
    rows: list[DeviceActivityRow]
    truncated: bool


class SecretAccessRow(BaseModel):
    ts: datetime
    user_email: str | None
    device_id: UUID
    device_name: str | None
    secret_kind: SecretKind
    secret_identifier: str
    secret_label: str | None
    last_rotation_ts: datetime | None
    rotated_since_reveal: bool
    ip_address: str | None
    justification: str | None


class SecretAccessReport(BaseModel):
    range_from: datetime
    range_to: datetime
    rows: list[SecretAccessRow]
    unrotated_count: int


class ChangeRow(BaseModel):
    ts: datetime
    user_email: str | None
    section: str
    action: str
    outcome: AuditOutcome
    device_id: UUID | None
    device_name: str | None
    request_payload: dict[str, Any] | None


class ChangeReport(BaseModel):
    range_from: datetime
    range_to: datetime
    rows: list[ChangeRow]
    by_section: dict[str, int]
    by_user: dict[str, int]
    truncated: bool
