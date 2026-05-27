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
    started_at_iso: str | None
    finished_at_iso: str | None
    log_tail: list[str]


class TriggerUpdateRequest(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    backup: bool = True
