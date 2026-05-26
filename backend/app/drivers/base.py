"""
Abstract VendorDriver — the contract every vendor implementation must satisfy.

The API layer never imports a concrete driver. It resolves the right one
through `registry.get_driver(device.vendor)` and calls Protocol methods on it.
This keeps the API surface stable as new vendors are added.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class Capability(StrEnum):
    """Sections a driver may support. The UI hides sections the active driver lacks."""

    # System
    SYSTEM_INFO = "system.info"
    SYSTEM_REBOOT = "system.reboot"
    SYSTEM_BACKUP = "system.backup"
    SYSTEM_USER = "system.user"        # device users (router-local accounts)
    # IP
    INTERFACE_LIST = "interface.list"
    IP_ADDRESS = "ip.address"
    IP_ROUTE = "ip.route"
    IP_SERVICE = "ip.service"           # api, ssh, www, winbox, …
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
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DhcpLease:
    address: str
    mac_address: str
    host_name: str | None = None
    client_id: str | None = None
    status: str | None = None
    server: str | None = None
    expires_at_iso: str | None = None
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
class NtpClient:
    """RouterOS /system/ntp/client (singleton)."""

    enabled: bool
    mode: str | None = None
    servers: str | None = None           # comma-separated server-dns-names (RouterOS 7)
    primary: str | None = None           # legacy 6.x primary-ntp
    secondary: str | None = None         # legacy 6.x secondary-ntp
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


@runtime_checkable
class VendorDriver(Protocol):
    """All vendor drivers conform to this interface."""

    vendor: str
    display_name: str
    capabilities: set[Capability]

    # core
    async def test_connection(self, creds: DeviceCredentials) -> bool: ...
    async def system_info(self, creds: DeviceCredentials) -> SystemInfo: ...

    # DHCP / firewall
    async def dhcp_leases(self, creds: DeviceCredentials) -> list[DhcpLease]: ...
    async def firewall_nat_list(self, creds: DeviceCredentials) -> list[NatRule]: ...
    async def firewall_nat_add(self, creds: DeviceCredentials, rule: NatRule) -> str: ...
    async def firewall_nat_remove(self, creds: DeviceCredentials, rule_id: str) -> None: ...
    async def firewall_filter_list(self, creds: DeviceCredentials) -> list[FilterRule]: ...
    async def firewall_filter_add(
        self, creds: DeviceCredentials, rule: FilterRule
    ) -> str: ...
    async def firewall_filter_set(
        self, creds: DeviceCredentials, rule_id: str, *, disabled: bool | None = None
    ) -> None: ...
    async def firewall_filter_remove(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None: ...

    # System logs
    async def log_list(
        self,
        creds: DeviceCredentials,
        *,
        topics: str | None = None,
        limit: int = 200,
    ) -> list[LogEntry]: ...

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
