from __future__ import annotations

from typing import Literal
from uuid import UUID  # noqa: F401  (kept for future per-rule operations)

from pydantic import BaseModel, Field


class FilterRulePublic(BaseModel):
    id: str | None
    chain: str
    action: str
    src_address: str | None
    dst_address: str | None
    src_address_list: str | None
    dst_address_list: str | None
    protocol: str | None
    src_port: str | None
    dst_port: str | None
    in_interface: str | None
    out_interface: str | None
    connection_state: str | None
    log: bool
    log_prefix: str | None
    bytes_count: int | None = None
    packets_count: int | None = None
    disabled: bool
    comment: str | None


class FilterRuleCreate(BaseModel):
    chain: Literal["input", "forward", "output"] = "forward"
    action: Literal[
        "accept", "drop", "reject", "fasttrack-connection", "log", "passthrough"
    ] = "accept"
    src_address: str | None = Field(default=None, max_length=64)
    dst_address: str | None = Field(default=None, max_length=64)
    src_address_list: str | None = Field(default=None, max_length=64)
    dst_address_list: str | None = Field(default=None, max_length=64)
    protocol: str | None = Field(default=None, max_length=16)
    src_port: str | None = Field(default=None, max_length=64)
    dst_port: str | None = Field(default=None, max_length=64)
    in_interface: str | None = Field(default=None, max_length=64)
    out_interface: str | None = Field(default=None, max_length=64)
    connection_state: str | None = Field(default=None, max_length=64)
    log: bool = False
    log_prefix: str | None = Field(default=None, max_length=64)
    disabled: bool = False
    comment: str | None = Field(default=None, max_length=255)


class FilterRuleUpdate(BaseModel):
    disabled: bool | None = None
    log: bool | None = None
    log_prefix: str | None = Field(default=None, max_length=64)


# ---------------- NAT ----------------


class NatRulePublic(BaseModel):
    id: str | None
    chain: str
    action: str
    src_address: str | None
    dst_address: str | None
    dst_port: str | None
    protocol: str | None
    to_addresses: str | None
    to_ports: str | None
    in_interface: str | None
    out_interface: str | None
    log: bool = False
    log_prefix: str | None = None
    bytes_count: int | None = None
    packets_count: int | None = None
    disabled: bool
    comment: str | None


class NatRuleCreate(BaseModel):
    chain: Literal["srcnat", "dstnat", "output"] = "dstnat"
    action: Literal[
        "accept",
        "masquerade",
        "src-nat",
        "dst-nat",
        "redirect",
        "netmap",
        "same",
        "jump",
        "return",
        "log",
        "passthrough",
    ] = "dst-nat"
    src_address: str | None = Field(default=None, max_length=128)
    dst_address: str | None = Field(default=None, max_length=128)
    dst_port: str | None = Field(default=None, max_length=64)
    protocol: str | None = Field(default=None, max_length=16)
    to_addresses: str | None = Field(default=None, max_length=128)
    to_ports: str | None = Field(default=None, max_length=64)
    in_interface: str | None = Field(default=None, max_length=64)
    out_interface: str | None = Field(default=None, max_length=64)
    log: bool = False
    log_prefix: str | None = Field(default=None, max_length=64)
    disabled: bool = False
    comment: str | None = Field(default=None, max_length=255)


class NatRuleUpdate(BaseModel):
    disabled: bool | None = None
    log: bool | None = None
    log_prefix: str | None = Field(default=None, max_length=64)


class LogEntryPublic(BaseModel):
    time: str
    topics: str
    message: str
