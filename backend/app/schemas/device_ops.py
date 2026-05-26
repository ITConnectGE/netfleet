from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------- IP services ----------------


class IpServicePublic(BaseModel):
    name: str
    port: int
    enabled: bool
    address: str | None = None
    certificate: str | None = None
    tls_only: bool | None = None


class IpServiceUpdate(BaseModel):
    enabled: bool | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    address: str | None = Field(default=None, max_length=255)


# ---------------- Device users ----------------


class DeviceUserPublic(BaseModel):
    id: str | None
    name: str
    group: str | None
    disabled: bool
    comment: str | None
    last_logged_in: str | None


class DeviceUserPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=512)


class DeviceUserDisableRequest(BaseModel):
    disabled: bool


# ---------------- Bulk ----------------


class BulkPasswordResetRequest(BaseModel):
    device_ids: list[UUID] = Field(min_length=1, max_length=500)
    username: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=8, max_length=512)


class BulkOperationResult(BaseModel):
    device_id: UUID
    device_name: str | None
    status: Literal["ok", "failed", "skipped"]
    error: str | None = None


class BulkPasswordResetResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    skipped: int
    results: list[BulkOperationResult]
