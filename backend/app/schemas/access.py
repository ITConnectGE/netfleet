"""Public shapes for the access-resolver service.

The frontend renders these on the tenant / site / device detail pages
and on the per-user access report. Kept separate from user.py to keep
each schema module focused on one concern.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

ScopeKind = Literal["organization", "tenant", "site", "device"]


class AccessEntryPublic(BaseModel):
    user_id: UUID
    email: EmailStr
    display_name: str | None
    is_admin: bool
    role_id: UUID | None
    role_name: str | None
    source_scope_type: ScopeKind | None
    source_scope_id: UUID | None
    source_scope_label: str | None


class AccessReportPublic(BaseModel):
    scope_type: ScopeKind
    scope_id: UUID | None
    scope_label: str
    entries: list[AccessEntryPublic]


# ---------------- Per-user map ----------------


class UserScopeGrantPublic(BaseModel):
    role_id: UUID | None
    role_name: str | None
    via_scope_type: ScopeKind | None
    via_scope_id: UUID | None
    via_scope_label: str | None


class UserAccessDevicePublic(BaseModel):
    device_id: UUID
    device_name: str
    grants: list[UserScopeGrantPublic]


class UserAccessSitePublic(BaseModel):
    site_id: UUID
    site_name: str
    grants: list[UserScopeGrantPublic]
    devices: list[UserAccessDevicePublic]


class UserAccessTenantPublic(BaseModel):
    tenant_id: UUID
    tenant_name: str
    grants: list[UserScopeGrantPublic]
    sites: list[UserAccessSitePublic]


class PermissionTuple(BaseModel):
    section: str
    action: str


class UserAccessMapPublic(BaseModel):
    user_id: UUID
    tenants: list[UserAccessTenantPublic]
    permissions: list[PermissionTuple]
