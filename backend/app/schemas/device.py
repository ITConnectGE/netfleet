from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.device import DeviceStatus, DeviceTransport


class DeviceBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=8728, ge=1, le=65535)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    transport: DeviceTransport = DeviceTransport.API
    verify_tls: bool = True
    notes: str | None = Field(default=None, max_length=2048)


class DeviceCreate(DeviceBase):
    site_id: UUID
    vendor: str = Field(min_length=1, max_length=32)
    username: str = Field(min_length=1, max_length=64)
    password: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _require_credential(self) -> DeviceCreate:
        if not self.password and not self.api_key:
            raise ValueError("either password or api_key must be provided")
        return self


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    transport: DeviceTransport | None = None
    verify_tls: bool | None = None
    username: str | None = Field(default=None, min_length=1, max_length=64)
    password: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=512)
    site_id: UUID | None = None
    is_enabled: bool | None = None
    notes: str | None = Field(default=None, max_length=2048)


class DevicePublic(BaseModel):
    """Device representation safe to return — never includes credentials."""

    id: UUID
    organization_id: UUID
    site_id: UUID
    vendor: str
    name: str
    host: str
    port: int
    ssh_port: int = 22
    transport: DeviceTransport
    verify_tls: bool
    username: str
    has_password: bool
    has_api_key: bool
    model: str | None
    serial: str | None
    firmware: str | None
    firmware_available: str | None
    firmware_checked_at: datetime | None
    routerboard_current: str | None
    routerboard_available: str | None
    status: DeviceStatus
    status_error: str | None
    last_seen_at: datetime | None
    is_enabled: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TestConnectionResult(BaseModel):
    ok: bool
    status: Literal["online", "offline", "error"]
    error: str | None = None
    identity: str | None = None
    model: str | None = None
    firmware: str | None = None
    uptime_seconds: int | None = None
