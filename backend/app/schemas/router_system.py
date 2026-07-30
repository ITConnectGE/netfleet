from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------- NTP ----------------


class NtpClientPublic(BaseModel):
    enabled: bool
    mode: str | None
    servers: str | None
    primary: str | None
    secondary: str | None
    # "systemd-timesyncd" | "chrony" | "unknown". Which daemon actually
    # keeps the clock — without it "NTP: enabled" says nothing about where
    # the time is coming from, and the server list can only be edited for
    # one of them.
    provider: str | None = None
    # Whether the host currently considers itself in sync, and which server
    # it is talking to right now, as opposed to the configured list.
    synchronized: bool | None = None
    server_name: str | None = None
    server_address: str | None = None


class NtpClientUpdate(BaseModel):
    enabled: bool | None = None
    mode: Literal["unicast", "broadcast", "multicast", "manycast"] | None = None
    servers: str | None = Field(default=None, max_length=512)
    primary: str | None = Field(default=None, max_length=64)
    secondary: str | None = Field(default=None, max_length=64)


class NtpServerPublic(BaseModel):
    enabled: bool
    broadcast: bool | None
    multicast: bool | None
    manycast: bool | None
    auth_key: str | None


class NtpServerUpdate(BaseModel):
    enabled: bool | None = None
    broadcast: bool | None = None
    multicast: bool | None = None
    manycast: bool | None = None


class DeviceClockPublic(BaseModel):
    time: str | None
    date: str | None
    time_zone_name: str | None
    time_zone_autodetect: bool | None
    gmt_offset: str | None
    dst_active: bool | None


class DeviceClockUpdate(BaseModel):
    """RouterOS accepts the IANA tz database name verbatim
    (Asia/Tbilisi, Europe/London, …) or the literal "manual" for an
    offset-only configuration."""

    time_zone_name: str | None = Field(default=None, max_length=64)
    time_zone_autodetect: bool | None = None


# ---------------- SNMP ----------------


class SnmpPublic(BaseModel):
    enabled: bool
    contact: str | None
    location: str | None
    trap_target: str | None
    trap_version: str | None
    engine_id: str | None


class SnmpUpdate(BaseModel):
    enabled: bool | None = None
    contact: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    trap_target: str | None = Field(default=None, max_length=255)
    trap_version: Literal["1", "2", "3"] | None = None


class SnmpCommunityPublic(BaseModel):
    id: str | None
    name: str
    addresses: str | None
    security: str | None
    read_access: bool
    write_access: bool
    disabled: bool


class SnmpCommunityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    addresses: str | None = Field(default=None, max_length=255)
    security: Literal["none", "authorized", "private"] | None = None
    read_access: bool = True
    write_access: bool = False


class SnmpCommunityUpdate(BaseModel):
    """All-optional patch. Renaming a community is allowed because RouterOS
    keys rows by `.id` internally, not by name."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    addresses: str | None = Field(default=None, max_length=255)
    security: Literal["none", "authorized", "private"] | None = None
    read_access: bool | None = None
    write_access: bool | None = None
    disabled: bool | None = None


# ---------------- /system/logging ----------------


class LoggingRulePublic(BaseModel):
    id: str | None
    topics: str
    action: str
    prefix: str | None = None
    disabled: bool
    invalid: bool = False
    default: bool = False


class LoggingRuleCreate(BaseModel):
    topics: str = Field(min_length=1, max_length=255)
    action: str = Field(min_length=1, max_length=64)
    prefix: str | None = Field(default=None, max_length=64)
    disabled: bool = False


class LoggingRuleUpdate(BaseModel):
    topics: str | None = Field(default=None, max_length=255)
    action: str | None = Field(default=None, max_length=64)
    prefix: str | None = Field(default=None, max_length=64)
    disabled: bool | None = None


class LoggingActionPublic(BaseModel):
    id: str | None
    name: str
    target: str
    remote: str | None = None
    remote_port: int | None = None
    src_address: str | None = None
    bsd_syslog: bool | None = None
    syslog_facility: str | None = None
    syslog_severity: str | None = None
    memory_lines: int | None = None
    disk_lines_per_file: int | None = None
    disk_file_count: int | None = None
    default: bool = False


class LoggingActionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    target: Literal["memory", "disk", "echo", "remote"]
    # Remote syslog config — required when target=remote
    remote: str | None = Field(default=None, max_length=64)
    remote_port: int | None = Field(default=None, ge=1, le=65535)
    src_address: str | None = Field(default=None, max_length=64)
    bsd_syslog: bool | None = None
    syslog_facility: str | None = Field(default=None, max_length=32)
    syslog_severity: str | None = Field(default=None, max_length=16)
    memory_lines: int | None = Field(default=None, ge=10, le=100000)


class SystemResourcesPublic(BaseModel):
    """Live resource snapshot read from the device on request.

    Vendor-neutral: RouterOS fills the percentages, a Linux host fills the
    absolute figures too. Everything is optional because a field the
    platform cannot report should be absent rather than zero — "0 GiB of
    RAM" is a lie, "—" is the truth.
    """

    identity: str
    model: str | None = None
    serial: str | None = None
    firmware: str | None = None
    os_family: str | None = None
    os_version: str | None = None
    uptime_seconds: int | None = None
    cpu_count: int | None = None
    cpu_load_pct: float | None = None
    load_avg_1: float | None = None
    load_avg_5: float | None = None
    load_avg_15: float | None = None
    memory_used_pct: float | None = None
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    swap_total_bytes: int | None = None
    swap_used_bytes: int | None = None


class DiskUsagePublic(BaseModel):
    filesystem: str
    mount_point: str
    fs_type: str | None = None
    total_bytes: int | None = None
    used_bytes: int | None = None
    available_bytes: int | None = None
    used_pct: float | None = None
    inodes_total: int | None = None
    inodes_used: int | None = None
    inodes_used_pct: float | None = None


class DirEntryUsagePublic(BaseModel):
    path: str
    name: str
    size_bytes: int
    is_dir: bool = True


class NtpSyncResult(BaseModel):
    message: str


class InterfaceConfigPublic(BaseModel):
    """One interface's addressing, denormalised on purpose — an operator
    asking "what is eth0 doing" wants address, method, gateway and
    resolvers together rather than joining four tables in their head."""

    name: str
    mac_address: str | None = None
    state: str | None = None
    admin_up: bool | None = None
    mtu: int | None = None
    type: str | None = None
    vlan_id: int | None = None
    vlan_parent: str | None = None
    method: str | None = None
    addresses: list[str] = []
    netmask: str | None = None
    gateway: str | None = None
    dns_servers: list[str] = []
    dns_search: list[str] = []
    dhcp_server: str | None = None
    lease_expires_iso: str | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    managed_by: str | None = None


class ProcessPublic(BaseModel):
    pid: int
    user: str | None = None
    cpu_pct: float | None = None
    mem_pct: float | None = None
    rss_bytes: int | None = None
    state: str | None = None
    started: str | None = None
    cpu_time: str | None = None
    command: str = ""
    threads: int | None = None
