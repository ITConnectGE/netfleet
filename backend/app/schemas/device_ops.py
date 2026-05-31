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


# ---------------- Bulk address list (P21 #13) ----------------


class BulkAddressListAddRequest(BaseModel):
    device_ids: list[UUID] = Field(min_length=1, max_length=500)
    list_name: str = Field(min_length=1, max_length=64)
    address: str = Field(min_length=1, max_length=128)
    timeout: str | None = Field(default=None, max_length=16)
    comment: str | None = Field(default=None, max_length=255)


class BulkAddressListAddResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    skipped: int
    results: list[BulkOperationResult]


# ---------------- Bulk firewall filter (P21 #13) ----------------


class BulkFilterRule(BaseModel):
    chain: str = Field(min_length=1, max_length=32)
    action: str = Field(min_length=1, max_length=32)
    src_address: str | None = Field(default=None, max_length=128)
    dst_address: str | None = Field(default=None, max_length=128)
    src_address_list: str | None = Field(default=None, max_length=64)
    dst_address_list: str | None = Field(default=None, max_length=64)
    protocol: str | None = Field(default=None, max_length=16)
    src_port: str | None = Field(default=None, max_length=64)
    dst_port: str | None = Field(default=None, max_length=64)
    in_interface: str | None = Field(default=None, max_length=64)
    out_interface: str | None = Field(default=None, max_length=64)
    connection_state: str | None = Field(default=None, max_length=64)
    log: bool = False
    log_prefix: str | None = Field(default=None, max_length=64)
    disabled: bool = False
    comment: str | None = Field(default=None, max_length=255)


class BulkFirewallFilterRequest(BaseModel):
    device_ids: list[UUID] = Field(min_length=1, max_length=500)
    rule: BulkFilterRule


class BulkFirewallFilterResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    skipped: int
    results: list[BulkOperationResult]
