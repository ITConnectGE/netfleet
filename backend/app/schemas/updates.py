from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UpdateStatusPublic(BaseModel):
    current: str
    available: str | None
    target_version: str | None
    channel: str
    repo: str
    state: Literal[
        "idle",
        "checking",
        "backing_up",
        "pulling",
        "recreating",
        "health_checking",
        "success",
        "failed",
    ]
    last_checked_iso: str | None
    last_error: str | None
    # Set when the release poll failed. Distinguishes "you are on the newest
    # release" from "we could not find out" — `available: null` means both.
    # Defaulted so an older updater container, which does not send the
    # field, still validates during the window between image recreations.
    check_error: str | None = None
    started_at_iso: str | None
    finished_at_iso: str | None
    log_tail: list[str]


class TriggerUpdateRequest(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    backup: bool = True
