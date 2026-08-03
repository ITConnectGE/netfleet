from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.device import BecomeMethod, DeviceClass, DeviceStatus, DeviceTransport

# Vendors whose devices are servers rather than network gear. Kept here
# rather than derived from the driver so validation does not depend on
# driver import order.
SERVER_VENDORS = {"linux"}

# Device identifiers are interpolated into the onboarding scripts that
# operators run as root. The generators quote everything they emit, but a
# control character (a newline above all) changes the *structure* of the
# output rather than a value inside it — a newline in a name can append a
# second key to a remote authorized_keys, which no amount of quoting
# prevents. So they are rejected at the edge as well.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
# POSIX-portable account name. Applied to servers only: RouterOS accepts a
# far wider charset and existing MikroTik devices must keep working.
_POSIX_USERNAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def _reject_control_chars(value: str | None, field: str) -> str | None:
    if value is not None and _CONTROL_CHARS.search(value):
        raise ValueError(f"{field} must not contain control characters or newlines")
    return value


def assert_posix_username(username: str) -> str:
    """Enforce the account-name rule for hosts where NetFleet's onboarding
    script will run `useradd`. Exported because `DeviceUpdate` carries no
    vendor field — the service layer applies it once the device is known."""
    if not _POSIX_USERNAME.match(username):
        raise ValueError(
            "username for a Linux host must match ^[a-z_][a-z0-9_-]{0,31}$ — "
            "the onboarding script creates this account with useradd"
        )
    return username


class DeviceBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=8728, ge=1, le=65535)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    transport: DeviceTransport = DeviceTransport.API
    verify_tls: bool = True
    notes: str | None = Field(default=None, max_length=2048)

    @field_validator("name", "host")
    @classmethod
    def _no_control_chars(cls, v: str, info: Any) -> str:
        return _reject_control_chars(v, info.field_name)  # type: ignore[return-value]


class DeviceCreate(DeviceBase):
    site_id: UUID
    vendor: str = Field(min_length=1, max_length=32)
    username: str = Field(min_length=1, max_length=64)
    password: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=512)
    # SSH hosts: leave both credential fields empty and NetFleet generates
    # a keypair, handing the public half to the onboarding script.
    generate_ssh_key: bool = False
    ssh_private_key: str | None = Field(default=None, max_length=16384)
    become_method: BecomeMethod = BecomeMethod.NONE
    become_password: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def _validate_credentials(self) -> DeviceCreate:
        if self.vendor in SERVER_VENDORS:
            if self.transport is not DeviceTransport.SSH:
                raise ValueError(f"vendor '{self.vendor}' requires transport 'ssh'")
            if self.api_key:
                raise ValueError(f"vendor '{self.vendor}' does not use api_key auth")
            supplied = [
                bool(self.password),
                bool(self.ssh_private_key),
                self.generate_ssh_key,
            ]
            if sum(supplied) != 1:
                raise ValueError(
                    "exactly one of password, ssh_private_key or generate_ssh_key "
                    "must be provided"
                )
            assert_posix_username(self.username)
            # Keep the two port columns in step so the UI never shows a
            # RouterOS API port on a server.
            if self.port != self.ssh_port:
                self.port = self.ssh_port
            return self

        _reject_control_chars(self.username, "username")
        if self.generate_ssh_key or self.ssh_private_key:
            raise ValueError("SSH key auth is only supported on SSH-transport vendors")
        if not self.password and not self.api_key:
            raise ValueError("either password or api_key must be provided")
        return self

    @model_validator(mode="after")
    def _validate_become(self) -> DeviceCreate:
        if self.become_method is BecomeMethod.NONE and self.become_password:
            raise ValueError("become_password requires become_method='sudo'")
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
    ssh_private_key: str | None = Field(default=None, max_length=16384)
    become_method: BecomeMethod | None = None
    become_password: str | None = Field(default=None, max_length=512)
    # Clears the pinned host key so the next connection re-pins. Used after
    # a legitimate host rebuild.
    reset_host_key: bool = False

    @field_validator("name", "host", "username")
    @classmethod
    def _no_control_chars(cls, v: str | None, info: Any) -> str | None:
        return _reject_control_chars(v, info.field_name)
    site_id: UUID | None = None
    is_enabled: bool | None = None
    notes: str | None = Field(default=None, max_length=2048)


class DevicePublic(BaseModel):
    """Device representation safe to return — never includes credentials."""

    id: UUID
    organization_id: UUID
    site_id: UUID
    vendor: str
    device_class: DeviceClass
    name: str
    host: str
    port: int
    ssh_port: int = 22
    transport: DeviceTransport
    verify_tls: bool
    username: str
    has_password: bool
    has_api_key: bool
    has_ssh_key: bool
    become_method: BecomeMethod
    ssh_host_key_fingerprint: str | None
    model: str | None
    serial: str | None
    firmware: str | None
    os_family: str | None
    os_version: str | None
    # Cached by the nightly sweep and by opening a host's Packages
    # tab. Null means never checked, which the UI shows as such
    # rather than as zero.
    packages_manager: str | None = None
    packages_updates_count: int | None = None
    packages_security_count: int | None = None
    packages_reboot_required: bool = False
    packages_checked_at: datetime | None = None
    packages_check_error: str | None = None
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
