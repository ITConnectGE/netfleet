from __future__ import annotations

from pydantic import BaseModel, Field


class SimpleQueuePublic(BaseModel):
    id: str | None
    name: str
    target: str | None
    max_limit: str | None
    burst_limit: str | None
    burst_threshold: str | None
    burst_time: str | None
    parent: str | None
    priority: str | None
    bytes_in: int | None
    bytes_out: int | None
    disabled: bool
    comment: str | None


class SimpleQueueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    target: str | None = Field(default=None, max_length=255)
    max_limit: str | None = Field(
        default=None,
        max_length=64,
        description="upload/download in bps with suffixes, e.g. '10M/10M'",
    )
    burst_limit: str | None = Field(default=None, max_length=64)
    burst_threshold: str | None = Field(default=None, max_length=64)
    burst_time: str | None = Field(default=None, max_length=64)
    parent: str | None = Field(default=None, max_length=64)
    priority: str | None = Field(default=None, max_length=64)
    disabled: bool = False
    comment: str | None = Field(default=None, max_length=255)
