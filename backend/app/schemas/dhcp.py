"""DHCP schemas — pools, servers, networks, leases (P21 Stage 10 / #1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------- Pools ----------------


class DhcpPoolPublic(BaseModel):
    id: str | None
    name: str
    ranges: str
    next_pool: str | None
    comment: str | None


class DhcpPoolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    ranges: str = Field(min_length=1, max_length=512)
    next_pool: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=255)


class DhcpPoolUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    ranges: str | None = Field(default=None, max_length=512)
    next_pool: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=255)


# ---------------- Servers ----------------


class DhcpServerPublic(BaseModel):
    id: str | None
    name: str
    interface: str
    address_pool: str | None
    lease_time: str | None
    authoritative: str | None
    disabled: bool
    comment: str | None


class DhcpServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    interface: str = Field(min_length=1, max_length=64)
    address_pool: str | None = Field(default=None, max_length=64)
    lease_time: str | None = Field(default=None, max_length=32)
    authoritative: str | None = Field(default=None, max_length=32)
    disabled: bool = False
    comment: str | None = Field(default=None, max_length=255)


class DhcpServerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    interface: str | None = Field(default=None, max_length=64)
    address_pool: str | None = Field(default=None, max_length=64)
    lease_time: str | None = Field(default=None, max_length=32)
    authoritative: str | None = Field(default=None, max_length=32)
    disabled: bool | None = None
    comment: str | None = Field(default=None, max_length=255)


# ---------------- Networks ----------------


class DhcpNetworkPublic(BaseModel):
    id: str | None
    address: str
    gateway: str | None
    netmask: str | None
    dns_servers: str | None
    ntp_servers: str | None
    domain: str | None
    comment: str | None


class DhcpNetworkCreate(BaseModel):
    address: str = Field(min_length=1, max_length=64)
    gateway: str | None = Field(default=None, max_length=64)
    netmask: str | None = Field(default=None, max_length=32)
    dns_servers: str | None = Field(default=None, max_length=255)
    ntp_servers: str | None = Field(default=None, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    comment: str | None = Field(default=None, max_length=255)


class DhcpNetworkUpdate(BaseModel):
    address: str | None = Field(default=None, max_length=64)
    gateway: str | None = Field(default=None, max_length=64)
    netmask: str | None = Field(default=None, max_length=32)
    dns_servers: str | None = Field(default=None, max_length=255)
    ntp_servers: str | None = Field(default=None, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    comment: str | None = Field(default=None, max_length=255)


# ---------------- Leases ----------------


class DhcpLeasePublic(BaseModel):
    id: str | None
    address: str
    mac_address: str
    host_name: str | None
    client_id: str | None
    status: str | None
    server: str | None
    expires_at_iso: str | None
    dynamic: bool = False
    blocked: bool = False
    comment: str | None


class DhcpLeaseCommentUpdate(BaseModel):
    comment: str | None = Field(default=None, max_length=255)
