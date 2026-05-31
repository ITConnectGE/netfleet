"""Public shapes for the Request Access workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

ScopeKind = Literal["organization", "tenant", "site", "device"]
RequestStatus = Literal["pending", "approved", "denied", "cancelled"]


class AccessRequestCreate(BaseModel):
    """Submitted by a regular user wanting to reach a scope they don't
    currently have access to. ``scope_type == "organization"`` is
    rejected — org-wide grants are admin-only."""

    scope_type: Literal["tenant", "site", "device"]
    scope_id: UUID
    reason: str | None = Field(default=None, max_length=2048)


class AccessRequestGrantPublic(BaseModel):
    role_id: UUID
    role_name: str
    assignment_id: UUID
    expires_at: datetime | None


class AccessRequestPublic(BaseModel):
    id: UUID
    organization_id: UUID
    requester_user_id: UUID
    requester_email: EmailStr
    requester_display_name: str | None
    scope_type: ScopeKind
    scope_id: UUID | None
    scope_label: str | None
    reason: str | None
    status: RequestStatus
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
    decided_by_user_id: UUID | None
    decided_by_email: EmailStr | None
    granted_expires_at: datetime | None
    decision_note: str | None
    grants: list[AccessRequestGrantPublic]


class AccessRequestApprove(BaseModel):
    role_ids: list[UUID] = Field(min_length=1)
    expires_at: datetime | None = None
    note: str | None = Field(default=None, max_length=2048)


class AccessRequestDeny(BaseModel):
    note: str | None = Field(default=None, max_length=2048)


# ---------------- Directory ----------------
#
# Lightweight name+id listing of every tenant/site/device in the org,
# used by the "browse and request access" pane. Regular users get this
# even when they can't open the full detail for the target.


class DirectoryDevice(BaseModel):
    id: UUID
    name: str
    has_access: bool


class DirectorySite(BaseModel):
    id: UUID
    name: str
    has_access: bool
    devices: list[DirectoryDevice]


class DirectoryTenant(BaseModel):
    id: UUID
    name: str
    has_access: bool
    sites: list[DirectorySite]


class DirectoryReport(BaseModel):
    tenants: list[DirectoryTenant]
