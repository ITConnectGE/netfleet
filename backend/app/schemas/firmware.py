from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class FirmwareUpgradeRequest(BaseModel):
    """Targets are independent so the UI can offer separate buttons:

    - `routeros` (default): upgrade the RouterOS package only.
    - `routerboard`: upgrade only the RouterBOARD bootloader. Useful when
      RouterOS is already on the target version and only the bootloader
      lags behind.
    - `both`: upgrade RouterOS first, then the bootloader (two reboots).

    The legacy `include_routerboard=true` request is still accepted and
    treated as `target="both"`.
    """

    target: Literal["routeros", "routerboard", "both"] = "routeros"
    include_routerboard: bool = False

    @model_validator(mode="after")
    def _coerce_legacy_flag(self) -> "FirmwareUpgradeRequest":
        if self.include_routerboard and self.target == "routeros":
            # Caller used the old single-flag API: promote to "both".
            object.__setattr__(self, "target", "both")
        return self


class FirmwareUpgradeResult(BaseModel):
    triggered: bool
    will_reboot: bool
    from_version: str | None
    to_version: str | None
    message: str


class FirmwareUpgradeStatus(BaseModel):
    last_triggered_at: datetime | None
    last_status: str | None         # "pending" | "succeeded" | "failed"
    last_error: str | None
    last_from_version: str | None
    last_to_version: str | None


class AutoUpgradePolicyPublic(BaseModel):
    enabled: bool
    window_start_hour: int | None
    window_end_hour: int | None


class AutoUpgradePolicyUpdate(BaseModel):
    enabled: bool
    window_start_hour: int | None = Field(default=None, ge=0, le=23)
    window_end_hour: int | None = Field(default=None, ge=0, le=23)

    @model_validator(mode="after")
    def _window_pair(self) -> "AutoUpgradePolicyUpdate":
        # Both or neither — a half-set window is almost certainly user error.
        if (self.window_start_hour is None) ^ (self.window_end_hour is None):
            raise ValueError("window_start_hour and window_end_hour must be set together")
        return self
