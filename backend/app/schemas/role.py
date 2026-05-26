from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.role import AssignmentScope, PermissionAction


class PermissionInput(BaseModel):
    section: str = Field(min_length=1, max_length=64)
    action: PermissionAction


class PermissionPublic(PermissionInput):
    id: UUID

    model_config = {"from_attributes": True}


class RoleBase(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)


class RoleCreate(RoleBase):
    permissions: list[PermissionInput] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    permissions: list[PermissionInput] | None = None


class RolePublic(RoleBase):
    id: UUID
    organization_id: UUID
    is_system: bool
    permissions: list[PermissionPublic]
    assignment_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SectionInfo(BaseModel):
    section: str
    actions: list[Literal["read", "write", "execute"]]
    kind: Literal["app", "driver"]


class RoleAssignmentInput(BaseModel):
    role_id: UUID
    scope_type: AssignmentScope = AssignmentScope.ORGANIZATION
    scope_id: UUID | None = None


class RoleAssignmentPublic(BaseModel):
    id: UUID
    user_id: UUID
    role_id: UUID
    role_name: str
    scope_type: AssignmentScope
    scope_id: UUID | None
    scope_label: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
