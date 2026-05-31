from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------- NTP ----------------


class NtpClientPublic(BaseModel):
    enabled: bool
    mode: str | None
    servers: str | None
    primary: str | None
    secondary: str | None


class NtpClientUpdate(BaseModel):
    enabled: bool | None = None
    mode: Literal["unicast", "broadcast", "multicast", "manycast"] | None = None
    servers: str | None = Field(default=None, max_length=512)
    primary: str | None = Field(default=None, max_length=64)
    secondary: str | None = Field(default=None, max_length=64)


class NtpServerPublic(BaseModel):
    enabled: bool
    broadcast: bool | None
    multicast: bool | None
    manycast: bool | None
    auth_key: str | None


class NtpServerUpdate(BaseModel):
    enabled: bool | None = None
    broadcast: bool | None = None
    multicast: bool | None = None
    manycast: bool | None = None


class DeviceClockPublic(BaseModel):
    time: str | None
    date: str | None
    time_zone_name: str | None
    time_zone_autodetect: bool | None
    gmt_offset: str | None
    dst_active: bool | None


class DeviceClockUpdate(BaseModel):
    """RouterOS accepts the IANA tz database name verbatim
    (Asia/Tbilisi, Europe/London, …) or the literal "manual" for an
    offset-only configuration."""

    time_zone_name: str | None = Field(default=None, max_length=64)
    time_zone_autodetect: bool | None = None


# ---------------- SNMP ----------------


class SnmpPublic(BaseModel):
    enabled: bool
    contact: str | None
    location: str | None
    trap_target: str | None
    trap_version: str | None
    engine_id: str | None


class SnmpUpdate(BaseModel):
    enabled: bool | None = None
    contact: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    trap_target: str | None = Field(default=None, max_length=255)
    trap_version: Literal["1", "2", "3"] | None = None


class SnmpCommunityPublic(BaseModel):
    id: str | None
    name: str
    addresses: str | None
    security: str | None
    read_access: bool
    write_access: bool
    disabled: bool


class SnmpCommunityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    addresses: str | None = Field(default=None, max_length=255)
    security: Literal["none", "authorized", "private"] | None = None
    read_access: bool = True
    write_access: bool = False


class SnmpCommunityUpdate(BaseModel):
    """All-optional patch. Renaming a community is allowed because RouterOS
    keys rows by `.id` internally, not by name."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    addresses: str | None = Field(default=None, max_length=255)
    security: Literal["none", "authorized", "private"] | None = None
    read_access: bool | None = None
    write_access: bool | None = None
    disabled: bool | None = None
