from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------- Routes ----------------


class IpRoutePublic(BaseModel):
    id: str | None
    dst_address: str
    gateway: str | None
    distance: int | None
    routing_table: str | None
    pref_src: str | None
    active: bool | None
    dynamic: bool | None
    static: bool | None
    disabled: bool
    comment: str | None


class IpRouteCreate(BaseModel):
    dst_address: str = Field(min_length=1, max_length=64)
    gateway: str | None = Field(default=None, max_length=255)
    distance: int | None = Field(default=None, ge=1, le=255)
    routing_table: str | None = Field(default=None, max_length=64)
    pref_src: str | None = Field(default=None, max_length=64)
    disabled: bool = False
    comment: str | None = Field(default=None, max_length=255)


# ---------------- IP addresses (read-only for now) ----------------


class IpAddressPublic(BaseModel):
    id: str | None
    address: str
    network: str | None
    interface: str | None
    disabled: bool
    invalid: bool
    comment: str | None


# ---------------- ARP ----------------


class ArpPublic(BaseModel):
    id: str | None
    address: str
    mac_address: str | None
    interface: str | None
    complete: bool | None
    dynamic: bool | None
    invalid: bool | None
    comment: str | None


# ---------------- Neighbours (CDP / LLDP / MNDP) ----------------


class NeighborPublic(BaseModel):
    id: str | None
    interface: str | None
    address: str | None
    address6: str | None
    mac_address: str | None
    identity: str | None
    platform: str | None
    version: str | None
    board: str | None
    interface_name: str | None
    discovered_by: str | None
    age: str | None
    uptime: str | None


# ---------------- Bridge hosts ----------------


class BridgeHostPublic(BaseModel):
    id: str | None
    mac_address: str
    on_interface: str | None
    bridge: str | None
    age: str | None
    dynamic: bool | None
    external: bool | None


# ---------------- Interfaces ----------------


class InterfacePublic(BaseModel):
    id: str | None
    name: str
    type: str
    running: bool | None
    disabled: bool
    mac_address: str | None
    mtu: int | None
    actual_mtu: int | None
    rx_bytes: int | None
    tx_bytes: int | None
    comment: str | None


# ---------------- VLANs ----------------


class VlanPublic(BaseModel):
    id: str | None
    name: str
    interface: str
    vlan_id: int
    mtu: int | None
    disabled: bool
    comment: str | None


class VlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    interface: str = Field(min_length=1, max_length=64)
    vlan_id: int = Field(ge=1, le=4094)
    mtu: int | None = Field(default=None, ge=576, le=9000)
    comment: str | None = Field(default=None, max_length=255)
