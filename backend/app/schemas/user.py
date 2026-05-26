from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.role import AssignmentScope


class UserListItem(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str | None
    is_active: bool
    is_admin: bool
    totp_enrolled: bool
    auth_method: Literal["local", "oidc"]
    last_login_at: datetime | None
    created_at: datetime
    assignment_count: int = 0

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=512)
    is_admin: bool = False


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    is_admin: bool | None = None


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=12, max_length=512)


class AssignmentCreate(BaseModel):
    role_id: UUID
    scope_type: AssignmentScope = AssignmentScope.ORGANIZATION
    scope_id: UUID | None = None


class AssignmentPublic(BaseModel):
    id: UUID
    user_id: UUID
    role_id: UUID
    role_name: str
    scope_type: AssignmentScope
    scope_id: UUID | None
    scope_label: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
