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
    mobile_phone: str | None = None
    is_active: bool
    is_admin: bool
    totp_enrolled: bool
    otp_login_enabled: bool = False
    must_change_password: bool = False
    auth_method: Literal["local", "oidc"]
    last_login_at: datetime | None
    created_at: datetime
    assignment_count: int = 0

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=255)
    # Password is optional from Stage 3 on. When omitted, the service
    # generates a strong random one and sets must_change_password=True,
    # forcing the recipient through a change on first login.
    password: str | None = Field(default=None, min_length=12, max_length=512)
    mobile_phone: str | None = Field(default=None, max_length=32)
    is_admin: bool = False
    # Roles assigned at organisation scope when the user is invited.
    # Site- and device-level scopes still flow through the explicit
    # /assignments endpoint (Stage 5 will surface those at invite time).
    role_ids: list[UUID] = Field(default_factory=list)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    mobile_phone: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None
    is_admin: bool | None = None


class UserInviteResponse(BaseModel):
    """Returned by POST /users. When a password was auto-generated the
    plaintext is included exactly once. When `email_sent=True` the
    invitee has been mailed their credentials directly and the inviter
    shouldn't need to copy/paste them; otherwise the inviter falls back
    to handing the password over out-of-band."""

    user: UserListItem
    generated_password: str | None = None
    email_sent: bool = False


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=12, max_length=512)


class AssignmentCreate(BaseModel):
    role_id: UUID
    scope_type: AssignmentScope = AssignmentScope.ORGANIZATION
    scope_id: UUID | None = None


class AssignmentBulkScope(BaseModel):
    scope_type: AssignmentScope
    scope_id: UUID | None = None


class AssignmentBulkCreate(BaseModel):
    """Grant one role across many scopes in a single API call. Used by
    the multi-checkbox tree on the user detail page (P21 #18).
    Existing (user, role, scope_type, scope_id) rows are silently
    skipped — the operation is idempotent at the row level."""

    role_id: UUID
    scopes: list[AssignmentBulkScope] = Field(min_length=1)


class AssignmentPublic(BaseModel):
    id: UUID
    user_id: UUID
    role_id: UUID
    role_name: str
    scope_type: AssignmentScope
    scope_id: UUID | None
    scope_label: str | None = None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignmentBulkResult(BaseModel):
    created: int
    skipped_existing: int
    assignments: list[AssignmentPublic]
