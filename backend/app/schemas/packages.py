from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PackageUpdatePublic(BaseModel):
    name: str
    current_version: str | None = None
    candidate_version: str | None = None
    is_security: bool = False
    origin: str | None = None
    architecture: str | None = None


class PackageStatePublic(BaseModel):
    manager: str
    updates: list[PackageUpdatePublic] = []
    security_count: int = 0
    reboot_required: bool = False
    reboot_required_by: list[str] = []
    last_refreshed_iso: str | None = None


class PackageRunPublic(BaseModel):
    id: UUID
    kind: Literal["refresh", "upgrade"]
    state: Literal["running", "succeeded", "failed", "interrupted"]
    packages: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    output: str | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class PackageUpgradeRequest(BaseModel):
    """Empty `packages` means everything upgradable — the common case, and
    the one the UI's main button uses."""

    packages: list[str] = Field(default_factory=list, max_length=200)
    security_only: bool = False
