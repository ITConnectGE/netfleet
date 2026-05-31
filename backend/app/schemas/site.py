from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class SiteBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    address: str | None = Field(default=None, max_length=512)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2048)


class SiteCreate(SiteBase):
    tenant_id: UUID


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=512)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2048)
    tenant_id: UUID | None = None


class SitePublic(SiteBase):
    id: UUID
    organization_id: UUID
    tenant_id: UUID
    tenant_name: str | None = None
    device_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
