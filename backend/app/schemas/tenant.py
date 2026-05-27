from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class TenantBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    description: str | None = Field(default=None, max_length=1024)
    primary_contact_name: str | None = Field(default=None, max_length=255)
    primary_contact_email: EmailStr | None = None
    primary_contact_phone: str | None = Field(default=None, max_length=64)


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    primary_contact_name: str | None = Field(default=None, max_length=255)
    primary_contact_email: EmailStr | None = None
    primary_contact_phone: str | None = Field(default=None, max_length=64)


class TenantPublic(TenantBase):
    id: UUID
    organization_id: UUID
    site_count: int = 0
    device_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
