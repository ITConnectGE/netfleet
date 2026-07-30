"""
Abstract VendorDriver — the contract every vendor implementation must satisfy.

The API layer never imports a concrete driver. It resolves the right one
through `registry.get_driver(device.vendor)` and calls Protocol methods on it.
This keeps the API surface stable as new vendors are added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class Capability(StrEnum):
    """Sections a driver may support. The UI hides sections the active driver lacks."""

    # System
    SYSTEM_INFO = "system.info"
    SYSTEM_REBOOT = "system.reboot"
    SYSTEM_BACKUP = "system.backup"
    SYSTEM_USER = "system.user"        # device users (router-local accounts)
    SYSTEM_CLOCK = "system.clock"      # timezone + NTP client
    SYSTEM_LOG = "system.log"          # on-device log / journal viewer
    SYSTEM_SNMP = "system.snmp"
    # IP
    INTERFACE_LIST = "interface.list"
    # RouterOS groups interfaces into named lists (WAN, LAN…). No Linux
    # equivalent, so it needs its own capability rather than riding along
    # with INTERFACE_LIST.
    INTERFACE_LIST_MEMBER = "interface.list.member"
    INTERFACE_VLAN = "interface.vlan"
    IP_ADDRESS = "ip.address"
    IP_ADDRESS_CONFIG = "ip.address.config"  # method (dhcp/static), gateway, DNS
    IP_ROUTE = "ip.route"
    IP_SERVICE = "ip.service"           # api, ssh, www, winbox, …
    # Two genuinely different things that used to share one name: the ARP /
    # NDP cache the kernel keeps, versus peers a device advertises itself to
    # over a discovery protocol. A Linux host has the former and not the
    # latter, so conflating them put a "Neighbors (CDP/LLDP)" tab on servers.
    IP_ARP = "ip.arp"
    IP_NEIGHBOR = "ip.neighbor"         # CDP / LLDP / MNDP discovered peers
    BRIDGE_HOST = "bridge.host"
    # DHCP
    DHCP_SERVER = "dhcp.server"
    DHCP_LEASE = "dhcp.lease"
    # Firewall
    FIREWALL_FILTER = "firewall.filter"
    FIREWALL_NAT = "firewall.nat"
    FIREWALL_MANGLE = "firewall.mangle"
    # QoS
    QUEUE_SIMPLE = "queue.simple"
    QUEUE_TREE = "queue.tree"
    # Host resources (servers)
    DISK_USAGE = "disk.usage"
    PROC_LIST = "proc.list"
    CRON = "cron"           # crontabs + systemd timers
    # PPP / VPN
    PPP_SECRET = "ppp.secret"
    VPN_L2TP = "vpn.l2tp"
    VPN_PPTP = "vpn.pptp"
    VPN_IPSEC = "vpn.ipsec"
    VPN_OVPN = "vpn.ovpn"
    VPN_SSTP = "vpn.sstp"
    VPN_WIREGUARD_IFACE = "vpn.wireguard.interface"
    VPN_WIREGUARD_PEER = "vpn.wireguard.peer"
    # Tooling
    TOOL_PING = "tool.ping"
    TOOL_TRACEROUTE = "tool.traceroute"
    # Firmware
    SYSTEM_FIRMWARE = "system.firmware"   # check + upgrade
    # Secret reveal — a special "execute" capability gating /secrets/reveal
    SECRET_REVEAL = "secret.reveal"


@dataclass(slots=True)
class SystemInfo:
    identity: str
    model: str | None = None
    serial: str | None = None
    firmware: str | None = None
    uptime_seconds: int | None = None
    cpu_load_pct: float | None = None
    memory_used_pct: float | None = None
    # Servers only. On a Linux host `firmware` carries the kernel release
    # and these carry the distro, so the device row can show something
    # more useful than "6.8.0-generic".
    os_family: str | None = None
    os_version: str | None = None
    # Absolute figures alongside the percentages. "84% of what?" is the
    # first question anyone asks of a memory bar, and RouterOS reports
    # these too — they were simply never carried through.
    cpu_count: int | None = None
    load_avg_1: float | None = None
    load_avg_5: float | None = None
    load_avg_15: float | None = None
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    swap_total_bytes: int | None = None
    swap_used_bytes: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceConfig:
    """Everything about one interface's addressing in a single row.

    Deliberately denormalised: an operator asking "what is eth0 doing"
    wants the address, whether it was leased or configured, the gateway
    and the resolvers together. Splitting them across four tables makes
    them join it in their head.
    """

    name: str
    mac_address: str | None = None
    state: str | None = None                 # UP / DOWN / UNKNOWN
    admin_up: bool | None = None
    mtu: int | None = None
    type: str | None = None                  # ether, bridge, vlan, wireguard…
    vlan_id: int | None = None
    vlan_parent: str | None = None
    # "dhcp" | "static" | "unmanaged" | "unknown"
    method: str | None = None
    addresses: list[str] = field(default_factory=list)   # ["10.0.0.5/24"]
    netmask: str | None = None               # dotted form of the first prefix
    gateway: str | None = None
    dns_servers: list[str] = field(default_factory=list)
    dns_search: list[str] = field(default_factory=list)
    dhcp_server: str | None = None
    lease_expires_iso: str | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    # Which subsystem owns this interface's configuration — netplan,
    # NetworkManager, systemd-networkd, ifupdown. Writing without knowing
    # this is how a change silently gets reverted on the next boot.
    managed_by: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScheduledJob:
    """One scheduled job, from cron or from a systemd timer.

    Both are represented in the same shape on purpose: on a current Ubuntu
    box much of what used to live in cron is now a timer, and an operator
    asking "what runs on this host at night" wants one answer, not two
    screens they have to reconcile.
    """

    # "user-crontab" | "system-crontab" | "cron.d" | "run-parts" | "timer"
    source: str
    schedule: str                    # "0 3 * * *", "@daily", "daily 06:00"
    command: str
    user: str | None = None
    enabled: bool = True
    origin: str | None = None        # file path or unit name
    unit: str | None = None          # timer unit, for source="timer"
    activates: str | None = None     # service the timer starts
    next_run_iso: str | None = None
    last_run_iso: str | None = None
    comment: str | None = None


@dataclass(slots=True)
class ProcessInfo:
    """One process, the way `top` and `htop` present them."""

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


@dataclass(slots=True)
class DirEntryUsage:
    """One child of a directory, with its recursive size."""

    path: str
    name: str
    size_bytes: int
    is_dir: bool = True


@dataclass(slots=True)
class DiskUsage:
    """One mounted filesystem. Inodes matter as much as bytes — a box can
    be at 30% of its capacity and still fail every write."""

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
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DhcpLease:
    address: str
    mac_address: str
    id: str | None = None
    host_name: str | None = None
    client_id: str | None = None
    status: str | None = None
    server: str | None = None
    expires_at_iso: str | None = None
    dynamic: bool = False
    blocked: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DhcpPool:
    id: str | None
    name: str
    ranges: str                              # "10.0.0.10-10.0.0.250"
    next_pool: str | None = None
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DhcpServer:
    id: str | None
    name: str
    interface: str
    address_pool: str | None = None
    lease_time: str | None = None            # "1d", "10m", etc.
    authoritative: str | None = None         # yes | no | after-2sec-delay (RouterOS)
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DhcpNetwork:
    id: str | None
    address: str                             # CIDR "10.0.0.0/24"
    gateway: str | None = None
    netmask: str | None = None
    dns_servers: str | None = None
    ntp_servers: str | None = None
    domain: str | None = None
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NatRule:
    id: str | None
    chain: str
    action: str
    src_address: str | None = None
    dst_address: str | None = None
    dst_port: str | None = None
    protocol: str | None = None
    to_addresses: str | None = None
    to_ports: str | None = None
    in_interface: str | None = None
    out_interface: str | None = None
    log: bool = False
    log_prefix: str | None = None
    bytes_count: int | None = None
    packets_count: int | None = None
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FilterRule:
    """A /ip/firewall/filter rule. Same shape on most vendors."""

    id: str | None
    chain: str                              # input | forward | output (+ custom)
    action: str                             # accept | drop | reject | log | jump | return
    src_address: str | None = None
    dst_address: str | None = None
    src_address_list: str | None = None
    dst_address_list: str | None = None
    protocol: str | None = None
    src_port: str | None = None
    dst_port: str | None = None
    in_interface: str | None = None
    out_interface: str | None = None
    connection_state: str | None = None     # new,established,related,invalid
    log: bool = False
    log_prefix: str | None = None
    bytes_count: int | None = None
    packets_count: int | None = None
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LogEntry:
    """One line from /log/print on RouterOS."""

    time: str                               # native string (jan/02 15:04:05 etc.)
    topics: str                             # comma-separated topics
    message: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoggingRule:
    """A /system/logging rule — what topics get logged where."""

    id: str | None
    topics: str                             # comma list; supports `!info` style negation
    action: str                             # name of a logging action (memory | disk | echo | remote_x)
    prefix: str | None = None               # optional string prepended to every line
    disabled: bool = False
    invalid: bool = False
    default: bool = False                   # RouterOS marks the seed rules with "default=yes"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoggingAction:
    """A /system/logging/action target — where matched lines are sent."""

    id: str | None
    name: str
    target: str                             # memory | disk | echo | remote | email
    remote: str | None = None               # syslog server IP (only when target=remote)
    remote_port: int | None = None
    src_address: str | None = None
    bsd_syslog: bool | None = None
    syslog_facility: str | None = None
    syslog_severity: str | None = None
    memory_lines: int | None = None
    disk_lines_per_file: int | None = None
    disk_file_count: int | None = None
    default: bool = False                   # built-in (memory/disk/echo) shouldn't be deleted
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IpRoute:
    id: str | None
    dst_address: str                       # "0.0.0.0/0", "192.168.1.0/24", ...
    gateway: str | None = None
    distance: int | None = None
    routing_table: str | None = None       # "main" by default
    pref_src: str | None = None
    vrf_interface: str | None = None
    active: bool | None = None
    dynamic: bool | None = None
    static: bool | None = None
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IpAddress:
    id: str | None
    address: str                           # e.g. "192.168.1.1/24"
    network: str | None = None
    interface: str | None = None
    disabled: bool = False
    invalid: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArpEntry:
    id: str | None
    address: str
    mac_address: str | None = None
    interface: str | None = None
    complete: bool | None = None
    dynamic: bool | None = None
    invalid: bool | None = None
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NeighborDiscoverySettings:
    """RouterOS /ip/neighbor/discovery-settings (singleton).

    `discover_interface_list` is either the literal "all" / "none" or a
    named interface-list (e.g. "WAN"). `protocols` is the comma-separated
    list of protocols to advertise + receive — typically
    "cdp,lldp,mndp" when discovery is on.
    """

    discover_interface_list: str | None
    protocols: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Neighbor:
    """One row from /ip/neighbor on RouterOS — a peer discovered via CDP,
    LLDP, or MikroTik's own MNDP. Other vendors use the same shape."""

    id: str | None
    interface: str | None                  # the local port the neighbour was seen on
    address: str | None                    # IPv4
    address6: str | None = None            # IPv6
    mac_address: str | None = None
    identity: str | None = None            # hostname / system-name
    platform: str | None = None            # "MikroTik" / "Cisco" / "Ubiquiti" / …
    version: str | None = None             # software version string
    board: str | None = None               # model / hardware identifier
    interface_name: str | None = None      # remote port the neighbour reports
    discovered_by: str | None = None       # "cdp" / "lldp" / "mndp" (comma-separated allowed)
    age: str | None = None                 # how long since last advert
    uptime: str | None = None              # the neighbour's own uptime
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BridgeHost:
    id: str | None
    mac_address: str
    on_interface: str | None = None        # the bridge port the MAC was learned on
    bridge: str | None = None
    age: str | None = None                 # e.g. "2m34s"
    dynamic: bool | None = None
    external: bool | None = None           # learned from another switch
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Interface:
    id: str | None
    name: str
    type: str                              # "ether", "wireguard", "vlan", "bridge", "ppp-out", ...
    running: bool | None = None
    disabled: bool = False
    mac_address: str | None = None
    mtu: int | None = None
    actual_mtu: int | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VlanInterface:
    id: str | None
    name: str
    interface: str                         # parent interface
    vlan_id: int
    mtu: int | None = None
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FirmwareInfo:
    """Result of asking the device about pending firmware updates."""

    current_version: str | None
    available_version: str | None
    channel: str | None                    # "stable" | "long-term" | "testing" | "development"
    routerboard_current: str | None = None
    routerboard_available: str | None = None
    status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SimpleQueue:
    """/queue/simple — per-IP or per-subnet bandwidth limit."""

    id: str | None
    name: str
    target: str | None = None              # comma-separated IPs/subnets
    max_limit: str | None = None           # "10M/10M" (upload/download)
    burst_limit: str | None = None
    burst_threshold: str | None = None
    burst_time: str | None = None
    parent: str | None = None              # for hierarchical queues
    priority: str | None = None            # "8/8" default
    bytes_in: int | None = None
    bytes_out: int | None = None
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NtpClient:
    """RouterOS /system/ntp/client (singleton)."""

    enabled: bool
    mode: str | None = None
    servers: str | None = None           # comma-separated server-dns-names (RouterOS 7)
    primary: str | None = None           # legacy 6.x primary-ntp
    secondary: str | None = None         # legacy 6.x secondary-ntp
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NtpServer:
    """RouterOS /system/ntp/server (singleton — router acting as NTP server)."""

    enabled: bool
    broadcast: bool | None = None
    multicast: bool | None = None
    manycast: bool | None = None
    auth_key: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DeviceClock:
    """Current device time as reported by /system/clock/print."""

    time: str | None                       # e.g. "12:34:56"
    date: str | None                       # e.g. "may/27/2026" (RouterOS format)
    time_zone_name: str | None
    time_zone_autodetect: bool | None
    gmt_offset: str | None                 # e.g. "+04:00"
    dst_active: bool | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SnmpSettings:
    """RouterOS /snmp (singleton)."""

    enabled: bool
    contact: str | None = None
    location: str | None = None
    trap_target: str | None = None
    trap_version: str | None = None      # "1" | "2" | "3"
    engine_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SnmpCommunity:
    id: str | None
    name: str
    addresses: str | None = None
    security: str | None = None          # "none" | "authorized" | "private"
    read_access: bool = True
    write_access: bool = False
    disabled: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IpService:
    name: str                  # "api", "ssh", "www", "winbox", …
    port: int
    enabled: bool
    address: str | None = None
    certificate: str | None = None
    tls_only: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DeviceUser:
    """A router-local user account (e.g. RouterOS /user/print)."""

    id: str | None
    name: str
    group: str | None = None
    disabled: bool = False
    comment: str | None = None
    last_logged_in: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PppSecret:
    """L2TP/PPTP/SSTP secret on RouterOS (i.e. a VPN credential)."""

    id: str | None
    name: str
    service: str               # "l2tp" / "pptp" / "sstp" / "ovpn" / "any"
    profile: str | None = None
    local_address: str | None = None
    remote_address: str | None = None
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WireguardInterface:
    id: str | None
    name: str
    listen_port: int | None = None
    private_key: str | None = None
    public_key: str | None = None
    mtu: int | None = None
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WireguardPeer:
    id: str | None
    interface: str
    public_key: str | None = None
    preshared_key: str | None = None
    allowed_address: str | None = None
    endpoint_address: str | None = None
    endpoint_port: int | None = None
    persistent_keepalive: int | None = None
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceList:
    """A /interface/list row — a named group of interfaces used in
    firewall, routing-mark and discovery rules."""

    id: str | None
    name: str
    include: str | None = None
    exclude: str | None = None
    dynamic: bool = False
    builtin: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterfaceListMember:
    """A /interface/list/member row — an interface's membership in a
    named list. One physical interface can belong to multiple lists."""

    id: str | None
    list: str
    interface: str
    dynamic: bool = False
    disabled: bool = False
    comment: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BackupArtifact:
    """The result of /system/backup/save + /export — both blobs."""

    backup_bytes: bytes        # binary .backup file
    rsc_text: str              # /export ASCII script
    timestamp_iso: str


@dataclass(slots=True)
class DeviceCredentials:
    """Decrypted, ready-to-use credentials for a single device connection."""

    host: str
    port: int
    username: str
    password: str | None = None
    api_key: str | None = None
    transport: str = "api"   # api | rest | ssh | netconf
    verify_tls: bool = True

    # SSH-transport fields. Ignored by API-transport drivers, so adding
    # them costs the MikroTik driver nothing. `ssh_port` is carried here
    # rather than passed per-call because an SSH driver needs it on every
    # single operation, not just backups.
    ssh_port: int = 22
    ssh_private_key: str | None = None       # OpenSSH PEM text
    ssh_key_passphrase: str | None = None
    become_method: str = "none"              # none | sudo
    become_password: str | None = None
    host_key_fingerprint: str | None = None  # pinned value; None = pin on first connect


class UnsupportedOperation(Exception):
    """The active driver does not implement the requested operation.

    A driver only implements the sections its platform actually has, so
    reaching for a missing one is expected rather than exceptional — the UI
    hides those sections, but a stale tab, a bookmark or a direct API call
    can still get through. Without this, the miss surfaces as
    `AttributeError: 'LinuxDriver' object has no attribute 'log_list'` and a
    500, which reads as a crash rather than "not applicable here".
    """


class SupportsCapabilityFallback:
    """Mixin turning a missing driver method into `UnsupportedOperation`.

    `__getattr__` runs only after normal attribute lookup fails, so an
    implemented method is untouched and there is no per-call cost.
    """

    vendor: str
    display_name: str

    def __getattr__(self, name: str) -> Any:
        # Dunder lookups must keep failing as AttributeError, or copy,
        # pickle and inspect start behaving strangely.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        raise UnsupportedOperation(
            f"{type(self).display_name} does not support '{name}'"
        )


@runtime_checkable
class VendorDriver(Protocol):
    """All vendor drivers conform to this interface."""

    vendor: str
    display_name: str
    capabilities: set[Capability]

    # core
    async def test_connection(self, creds: DeviceCredentials) -> bool: ...
    async def system_info(self, creds: DeviceCredentials) -> SystemInfo: ...
    async def disk_usage_list(self, creds: DeviceCredentials) -> list[DiskUsage]: ...
    async def disk_tree(
        self, creds: DeviceCredentials, path: str, *, depth: int = 1
    ) -> list[DirEntryUsage]: ...
    async def interface_configs(
        self, creds: DeviceCredentials
    ) -> list[InterfaceConfig]: ...
    async def ntp_sync_now(self, creds: DeviceCredentials) -> str: ...
    async def processes_top(
        self, creds: DeviceCredentials, *, limit: int = 40
    ) -> list[ProcessInfo]: ...
    async def scheduled_jobs(
        self, creds: DeviceCredentials
    ) -> list[ScheduledJob]: ...
    async def system_reboot(self, creds: DeviceCredentials) -> None:
        """Trigger a clean reboot of the device. Implementations should
        swallow the connection-drop that follows because the router
        terminates the API session before sending an explicit reply."""
        ...

    # DHCP / firewall
    async def dhcp_leases(self, creds: DeviceCredentials) -> list[DhcpLease]: ...
    async def dhcp_lease_make_static(
        self, creds: DeviceCredentials, lease_id: str
    ) -> None: ...
    async def dhcp_lease_set_comment(
        self, creds: DeviceCredentials, lease_id: str, *, comment: str | None
    ) -> None: ...
    async def dhcp_lease_remove(
        self, creds: DeviceCredentials, lease_id: str
    ) -> None: ...

    async def dhcp_pools_list(self, creds: DeviceCredentials) -> list[DhcpPool]: ...
    async def dhcp_pool_add(self, creds: DeviceCredentials, pool: DhcpPool) -> str: ...
    async def dhcp_pool_update(
        self, creds: DeviceCredentials, pool_id: str, pool: DhcpPool
    ) -> None: ...
    async def dhcp_pool_remove(self, creds: DeviceCredentials, pool_id: str) -> None: ...

    async def dhcp_servers_list(self, creds: DeviceCredentials) -> list[DhcpServer]: ...
    async def dhcp_server_add(self, creds: DeviceCredentials, server: DhcpServer) -> str: ...
    async def dhcp_server_update(
        self, creds: DeviceCredentials, server_id: str, server: DhcpServer
    ) -> None: ...
    async def dhcp_server_remove(self, creds: DeviceCredentials, server_id: str) -> None: ...

    async def dhcp_networks_list(self, creds: DeviceCredentials) -> list[DhcpNetwork]: ...
    async def dhcp_network_add(
        self, creds: DeviceCredentials, network: DhcpNetwork
    ) -> str: ...
    async def dhcp_network_update(
        self, creds: DeviceCredentials, network_id: str, network: DhcpNetwork
    ) -> None: ...
    async def dhcp_network_remove(
        self, creds: DeviceCredentials, network_id: str
    ) -> None: ...
    async def firewall_nat_list(self, creds: DeviceCredentials) -> list[NatRule]: ...
    async def firewall_nat_add(self, creds: DeviceCredentials, rule: NatRule) -> str: ...
    async def firewall_nat_set(
        self,
        creds: DeviceCredentials,
        rule_id: str,
        *,
        disabled: bool | None = None,
        log: bool | None = None,
        log_prefix: str | None = None,
    ) -> None: ...
    async def firewall_nat_remove(self, creds: DeviceCredentials, rule_id: str) -> None: ...
    async def firewall_nat_reset_counters(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None: ...
    async def interface_reset_counters(
        self, creds: DeviceCredentials, interface_name: str
    ) -> None: ...
    async def firewall_filter_list(self, creds: DeviceCredentials) -> list[FilterRule]: ...
    async def firewall_filter_add(
        self, creds: DeviceCredentials, rule: FilterRule
    ) -> str: ...
    async def firewall_filter_set(
        self,
        creds: DeviceCredentials,
        rule_id: str,
        *,
        disabled: bool | None = None,
        log: bool | None = None,
        log_prefix: str | None = None,
    ) -> None: ...
    async def firewall_filter_reset_counters(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None: ...
    async def firewall_filter_remove(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None: ...
    async def firewall_filter_move(
        self,
        creds: DeviceCredentials,
        rule_id: str,
        *,
        before_id: str | None = None,
    ) -> None:
        """Reorder a /ip/firewall/filter rule. ``before_id`` is the id
        of the rule the moved one should land *in front of* — pass
        ``None`` to move to the end of the chain."""
        ...
    async def firewall_address_list_add(
        self,
        creds: DeviceCredentials,
        *,
        list_name: str,
        address: str,
        comment: str | None = None,
        timeout: str | None = None,
    ) -> str: ...

    # System logs
    async def log_list(
        self,
        creds: DeviceCredentials,
        *,
        topics: str | None = None,
        limit: int = 200,
    ) -> list[LogEntry]: ...

    # IP routes
    async def ip_routes_list(self, creds: DeviceCredentials) -> list[IpRoute]: ...
    async def ip_route_add(self, creds: DeviceCredentials, route: IpRoute) -> str: ...
    async def ip_route_remove(self, creds: DeviceCredentials, route_id: str) -> None: ...

    # IP addresses
    async def ip_addresses_list(self, creds: DeviceCredentials) -> list[IpAddress]: ...
    async def ip_address_add(
        self,
        creds: DeviceCredentials,
        *,
        address: str,
        interface: str,
        comment: str | None = None,
    ) -> str: ...
    async def interface_list_members(
        self, creds: DeviceCredentials, list_name: str
    ) -> list[str]:
        """Return the names of interfaces belonging to the given
        ``/interface/list`` (e.g. ``WAN``, ``LAN``). Empty list when
        the named list doesn't exist on the device."""
        ...

    # ARP
    async def ip_arp_list(self, creds: DeviceCredentials) -> list[ArpEntry]: ...

    # Bridge hosts
    async def bridge_hosts_list(self, creds: DeviceCredentials) -> list[BridgeHost]: ...

    # CDP / LLDP / MNDP neighbour discovery
    async def ip_neighbors_list(self, creds: DeviceCredentials) -> list[Neighbor]: ...
    async def ip_neighbor_discovery_get(
        self, creds: DeviceCredentials
    ) -> NeighborDiscoverySettings: ...
    async def ip_neighbor_discovery_set(
        self,
        creds: DeviceCredentials,
        *,
        discover_interface_list: str | None = None,
        protocols: str | None = None,
    ) -> None: ...

    # Firmware
    async def firmware_check_updates(self, creds: DeviceCredentials) -> FirmwareInfo: ...
    async def firmware_upgrade(self, creds: DeviceCredentials) -> None:
        """Download + install pending RouterOS update. The device will reboot.

        Implementations should treat connection drops after triggering the
        install as expected — the upgrade is now in the device's hands.
        """
        ...
    async def firmware_routerboard_upgrade(self, creds: DeviceCredentials) -> None:
        """Apply the pending RouterBOARD bootloader upgrade. Reboots the device."""
        ...

    # Queues
    async def queue_simple_list(self, creds: DeviceCredentials) -> list[SimpleQueue]: ...
    async def queue_simple_add(
        self, creds: DeviceCredentials, queue: SimpleQueue
    ) -> str: ...
    async def queue_simple_remove(
        self, creds: DeviceCredentials, queue_id: str
    ) -> None: ...
    async def queue_simple_reset_counters(
        self, creds: DeviceCredentials, queue_id: str
    ) -> None: ...

    # Interfaces + VLANs
    async def interfaces_list(self, creds: DeviceCredentials) -> list[Interface]: ...
    async def vlan_list(self, creds: DeviceCredentials) -> list[VlanInterface]: ...
    async def vlan_add(self, creds: DeviceCredentials, vlan: VlanInterface) -> str: ...
    async def vlan_remove(self, creds: DeviceCredentials, vlan_id: str) -> None: ...

    # NTP
    async def ntp_client_get(self, creds: DeviceCredentials) -> NtpClient: ...
    async def ntp_client_set(
        self,
        creds: DeviceCredentials,
        *,
        enabled: bool | None = None,
        mode: str | None = None,
        servers: str | None = None,
        primary: str | None = None,
        secondary: str | None = None,
    ) -> None: ...
    async def ntp_server_get(self, creds: DeviceCredentials) -> NtpServer: ...
    async def ntp_server_set(
        self,
        creds: DeviceCredentials,
        *,
        enabled: bool | None = None,
        broadcast: bool | None = None,
        multicast: bool | None = None,
        manycast: bool | None = None,
    ) -> None: ...

    # Clock
    async def clock_get(self, creds: DeviceCredentials) -> DeviceClock: ...
    async def clock_set(
        self,
        creds: DeviceCredentials,
        *,
        time_zone_name: str | None = None,
        time_zone_autodetect: bool | None = None,
    ) -> None: ...

    # SNMP
    async def snmp_get(self, creds: DeviceCredentials) -> SnmpSettings: ...
    async def snmp_set(
        self,
        creds: DeviceCredentials,
        *,
        enabled: bool | None = None,
        contact: str | None = None,
        location: str | None = None,
        trap_target: str | None = None,
        trap_version: str | None = None,
    ) -> None: ...
    async def snmp_community_list(self, creds: DeviceCredentials) -> list[SnmpCommunity]: ...
    async def snmp_community_add(
        self, creds: DeviceCredentials, community: SnmpCommunity
    ) -> str: ...
    async def snmp_community_remove(
        self, creds: DeviceCredentials, community_id: str
    ) -> None: ...
    async def snmp_community_update(
        self,
        creds: DeviceCredentials,
        community_id: str,
        *,
        name: str | None = None,
        addresses: str | None = None,
        security: str | None = None,
        read_access: bool | None = None,
        write_access: bool | None = None,
        disabled: bool | None = None,
    ) -> None: ...

    # IP services
    async def ip_services_list(self, creds: DeviceCredentials) -> list[IpService]: ...
    async def ip_service_set(
        self,
        creds: DeviceCredentials,
        name: str,
        *,
        enabled: bool | None = None,
        port: int | None = None,
        address: str | None = None,
    ) -> None: ...

    # Device users
    async def device_users_list(self, creds: DeviceCredentials) -> list[DeviceUser]: ...
    async def device_user_set_password(
        self, creds: DeviceCredentials, username: str, new_password: str
    ) -> None: ...
    async def device_user_set_disabled(
        self, creds: DeviceCredentials, username: str, disabled: bool
    ) -> None: ...

    # PPP secrets (L2TP / PPTP / SSTP / OVPN)
    async def ppp_secrets_list(self, creds: DeviceCredentials) -> list[PppSecret]: ...
    async def ppp_secret_add(
        self, creds: DeviceCredentials, secret: PppSecret, password: str
    ) -> str: ...
    async def ppp_secret_set_password(
        self, creds: DeviceCredentials, secret_id: str, new_password: str
    ) -> None: ...
    async def ppp_secret_remove(self, creds: DeviceCredentials, secret_id: str) -> None: ...
    async def ppp_secret_reveal_password(
        self, creds: DeviceCredentials, secret_id: str
    ) -> str: ...

    # WireGuard
    async def wireguard_interfaces_list(
        self, creds: DeviceCredentials
    ) -> list[WireguardInterface]: ...
    async def wireguard_interface_add(
        self, creds: DeviceCredentials, iface: WireguardInterface
    ) -> str: ...
    async def wireguard_interface_remove(
        self, creds: DeviceCredentials, iface_id: str
    ) -> None: ...
    async def wireguard_peers_list(
        self, creds: DeviceCredentials, *, interface: str | None = None
    ) -> list[WireguardPeer]: ...
    async def wireguard_peer_add(
        self, creds: DeviceCredentials, peer: WireguardPeer
    ) -> str: ...
    async def wireguard_peer_remove(
        self, creds: DeviceCredentials, peer_id: str
    ) -> None: ...
    async def wireguard_peer_reveal_keys(
        self, creds: DeviceCredentials, peer_id: str
    ) -> dict[str, str | None]: ...

    # Backup
    async def system_backup(self, creds: DeviceCredentials) -> BackupArtifact: ...
    async def system_restore(
        self,
        creds: DeviceCredentials,
        *,
        local_backup_path: Path,
        ssh_port: int = 22,
    ) -> None:
        """Restore a previously-taken backup. Implementations upload the file
        out-of-band (SFTP/SCP) and trigger the vendor restore command. The
        device is expected to reboot — callers should treat connection drops
        right after this call as success."""
        ...
