from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=512)


class LoginResponseFinal(BaseModel):
    """Returned when the user has no TOTP enrolled — login is done."""

    status: Literal["ok"] = "ok"
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserPublic


class LoginResponseMfaRequired(BaseModel):
    """Returned when the user must complete TOTP. The temp_token has typ=mfa_temp and short TTL."""

    status: Literal["mfa_required"] = "mfa_required"
    mfa_temp_token: str
    mfa_temp_expires_at: datetime


class TotpVerifyRequest(BaseModel):
    mfa_temp_token: str
    code: str = Field(min_length=6, max_length=8, pattern=r"^\d+$")


class TotpEnrollResponse(BaseModel):
    """Returned when an enrolled user starts TOTP setup. The secret is shown ONCE."""

    secret: str
    otpauth_uri: str


class TotpEnrollConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8, pattern=r"^\d+$")


class TotpDisableRequest(BaseModel):
    """Disabling TOTP rechecks the password — a stolen-but-unlocked
    session shouldn't be able to weaken the second factor."""

    current_password: str = Field(min_length=1, max_length=512)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=12, max_length=512)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None  # also accepted via httpOnly cookie


class TokenPair(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class UserPublic(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str | None
    mobile_phone: str | None = None
    is_admin: bool
    totp_enrolled: bool
    must_change_password: bool = False
    auth_method: Literal["local", "oidc"]
    organization_id: UUID

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    """Fields the user can change about themselves from /dashboard/profile.

    Email, admin flag and auth_method are intentionally excluded — those
    are admin-only changes via /users/{id}.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    # E.164 with optional leading "+". Loose so callers can write
    # "+995 555 12 34 56"; we strip spaces server-side before saving.
    mobile_phone: str | None = Field(default=None, max_length=32)


class SetupRequest(BaseModel):
    """First-run setup. Creates the org + first admin user. Only allowed when DB is empty."""

    organization_name: str = Field(min_length=1, max_length=255)
    organization_slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    admin_email: EmailStr
    admin_display_name: str = Field(min_length=1, max_length=255)
    admin_password: str = Field(min_length=12, max_length=512)


class SetupResponse(BaseModel):
    organization_id: UUID
    user_id: UUID
    message: str = "Setup complete. You can now sign in."
