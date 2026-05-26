from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FirmwareStatusPublic(BaseModel):
    current_version: str | None
    available_version: str | None
    channel: str | None
    checked_at: datetime | None
    routerboard_current: str | None
    routerboard_available: str | None
    needs_upgrade: bool


class FleetFirmwareSummary(BaseModel):
    total: int
    updates_available: int
    checked_ever: int
    never_checked: int
