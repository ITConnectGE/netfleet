"""
MikroTik RouterOS driver.

Uses `librouteros` for the native API (works on 6.x and 7.x). REST API support
(7.x only, JSON over HTTPS) will be added as a transport fallback in a later phase.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from app.drivers.base import (
    ArpEntry,
    BackupArtifact,
    BridgeHost,
    Capability,
    DeviceClock,
    DeviceCredentials,
    DeviceUser,
    DhcpLease,
    DhcpNetwork,
    DhcpPool,
    DhcpServer,
    FilterRule,
    FirmwareInfo,
    Interface,
    InterfaceList,
    InterfaceListMember,
    IpAddress,
    IpRoute,
    IpService,
    LogEntry,
    LoggingAction,
    LoggingRule,
    NatRule,
    Neighbor,
    NeighborDiscoverySettings,
    NtpClient,
    NtpServer,
    PppSecret,
    SimpleQueue,
    SnmpCommunity,
    SnmpSettings,
    SystemInfo,
    VendorDriver,
    VlanInterface,
    WireguardInterface,
    WireguardPeer,
)

log = structlog.get_logger(__name__)


class MikrotikDriver:
    vendor: str = "mikrotik"
    display_name: str = "MikroTik RouterOS 7.x / 6.x"
    capabilities: set[Capability] = {
        Capability.SYSTEM_INFO,
        Capability.SYSTEM_REBOOT,
        Capability.SYSTEM_BACKUP,
        Capability.SYSTEM_USER,
        Capability.INTERFACE_LIST,
        Capability.IP_ADDRESS,
        Capability.IP_ROUTE,
        Capability.IP_SERVICE,
        Capability.IP_NEIGHBOR,
        Capability.DHCP_SERVER,
        Capability.DHCP_LEASE,
        Capability.FIREWALL_FILTER,
        Capability.FIREWALL_NAT,
        Capability.FIREWALL_MANGLE,
        Capability.QUEUE_SIMPLE,
        Capability.QUEUE_TREE,
        Capability.PPP_SECRET,
        Capability.VPN_L2TP,
        Capability.VPN_PPTP,
        Capability.VPN_IPSEC,
        Capability.VPN_SSTP,
        Capability.VPN_OVPN,
        Capability.VPN_WIREGUARD_IFACE,
        Capability.VPN_WIREGUARD_PEER,
        Capability.TOOL_PING,
        Capability.TOOL_TRACEROUTE,
        Capability.SYSTEM_FIRMWARE,
        Capability.SECRET_REVEAL,
    }

    # ============== core ==============

    async def test_connection(self, creds: DeviceCredentials) -> bool:
        try:
            await self._call(creds, "/system/identity/print")
            return True
        except Exception as e:
            log.warning("mikrotik.test_connection_failed", host=creds.host, error=str(e))
            return False

    async def system_info(self, creds: DeviceCredentials) -> SystemInfo:
        identity_rows = await self._call(creds, "/system/identity/print")
        resource_rows = await self._call(creds, "/system/resource/print")
        identity = (identity_rows[0] if identity_rows else {}).get("name", "")
        r = resource_rows[0] if resource_rows else {}

        # The serial number lives on /system/routerboard/print, not /resource.
        # CHR / x86 builds don't have a routerboard, so we tolerate the call
        # failing and just leave serial=None for those.
        serial = None
        rb_raw: dict[str, Any] = {}
        try:
            rb_rows = await self._call(creds, "/system/routerboard/print")
            if rb_rows:
                rb_raw = rb_rows[0]
                serial = rb_raw.get("serial-number")
        except Exception:
            pass

        return SystemInfo(
            identity=str(identity),
            model=r.get("board-name") or rb_raw.get("model"),
            serial=serial,
            firmware=r.get("version"),
            uptime_seconds=_parse_uptime(r.get("uptime", "")),
            cpu_load_pct=float(r.get("cpu-load", 0)) if r.get("cpu-load") else None,
            memory_used_pct=_pct_used(r.get("free-memory"), r.get("total-memory")),
            raw={**r, **(identity_rows[0] if identity_rows else {}), **rb_raw},
        )

    async def system_reboot(self, creds: DeviceCredentials) -> None:
        # The router terminates the API session right after enqueueing
        # the reboot, so the librouteros call almost always raises a
        # transport-level exception before it sees an OK. Swallow it —
        # the operator's intent has been honoured by the time we get
        # here.
        try:
            await self._call(creds, "/system/reboot")
        except Exception as e:  # noqa: BLE001
            msg = str(e).lower()
            if any(s in msg for s in ("not allowed", "no permission", "auth")):
                raise
            # Otherwise it's the expected "device went away" race.

    # ============== DHCP ==============

    async def dhcp_leases(self, creds: DeviceCredentials) -> list[DhcpLease]:
        rows = await self._call(creds, "/ip/dhcp-server/lease/print")
        return [
            DhcpLease(
                id=r.get(".id"),
                address=str(r.get("address", "")),
                mac_address=str(r.get("mac-address", "")),
                host_name=r.get("host-name"),
                client_id=r.get("client-id"),
                status=r.get("status"),
                server=r.get("server"),
                expires_at_iso=r.get("expires-after"),
                dynamic=_to_bool(r.get("dynamic")),
                blocked=_to_bool(r.get("blocked")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    async def dhcp_lease_make_static(
        self, creds: DeviceCredentials, lease_id: str
    ) -> None:
        await self._call(
            creds, "/ip/dhcp-server/lease/make-static", **{".id": lease_id}
        )

    async def dhcp_lease_set_comment(
        self, creds: DeviceCredentials, lease_id: str, *, comment: str | None
    ) -> None:
        await self._call(
            creds,
            "/ip/dhcp-server/lease/set",
            **{".id": lease_id, "comment": comment if comment is not None else ""},
        )

    async def dhcp_lease_remove(
        self, creds: DeviceCredentials, lease_id: str
    ) -> None:
        await self._call(
            creds, "/ip/dhcp-server/lease/remove", **{".id": lease_id}
        )

    # ---------------- DHCP pools ----------------

    async def dhcp_pools_list(self, creds: DeviceCredentials) -> list[DhcpPool]:
        rows = await self._call(creds, "/ip/pool/print")
        return [
            DhcpPool(
                id=r.get(".id"),
                name=str(r.get("name", "")),
                ranges=str(r.get("ranges", "")),
                next_pool=r.get("next-pool"),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    async def dhcp_pool_add(self, creds: DeviceCredentials, pool: DhcpPool) -> str:
        params: dict[str, Any] = {"name": pool.name, "ranges": pool.ranges}
        if pool.next_pool:
            params["next-pool"] = pool.next_pool
        if pool.comment is not None:
            params["comment"] = pool.comment
        rows = await self._call(creds, "/ip/pool/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def dhcp_pool_update(
        self, creds: DeviceCredentials, pool_id: str, pool: DhcpPool
    ) -> None:
        params: dict[str, Any] = {".id": pool_id}
        if pool.name:
            params["name"] = pool.name
        if pool.ranges:
            params["ranges"] = pool.ranges
        if pool.next_pool is not None:
            params["next-pool"] = pool.next_pool
        if pool.comment is not None:
            params["comment"] = pool.comment
        await self._call(creds, "/ip/pool/set", **params)

    async def dhcp_pool_remove(
        self, creds: DeviceCredentials, pool_id: str
    ) -> None:
        await self._call(creds, "/ip/pool/remove", **{".id": pool_id})

    # ---------------- DHCP servers ----------------

    async def dhcp_servers_list(self, creds: DeviceCredentials) -> list[DhcpServer]:
        rows = await self._call(creds, "/ip/dhcp-server/print")
        return [
            DhcpServer(
                id=r.get(".id"),
                name=str(r.get("name", "")),
                interface=str(r.get("interface", "")),
                address_pool=r.get("address-pool"),
                lease_time=r.get("lease-time"),
                authoritative=r.get("authoritative"),
                disabled=_to_bool(r.get("disabled")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    async def dhcp_server_add(
        self, creds: DeviceCredentials, server: DhcpServer
    ) -> str:
        params: dict[str, Any] = {
            "name": server.name,
            "interface": server.interface,
        }
        if server.address_pool:
            params["address-pool"] = server.address_pool
        if server.lease_time:
            params["lease-time"] = server.lease_time
        if server.authoritative:
            params["authoritative"] = server.authoritative
        if server.disabled:
            params["disabled"] = "yes"
        if server.comment is not None:
            params["comment"] = server.comment
        rows = await self._call(creds, "/ip/dhcp-server/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def dhcp_server_update(
        self, creds: DeviceCredentials, server_id: str, server: DhcpServer
    ) -> None:
        params: dict[str, Any] = {".id": server_id}
        if server.name:
            params["name"] = server.name
        if server.interface:
            params["interface"] = server.interface
        if server.address_pool is not None:
            params["address-pool"] = server.address_pool
        if server.lease_time is not None:
            params["lease-time"] = server.lease_time
        if server.authoritative is not None:
            params["authoritative"] = server.authoritative
        params["disabled"] = "yes" if server.disabled else "no"
        if server.comment is not None:
            params["comment"] = server.comment
        await self._call(creds, "/ip/dhcp-server/set", **params)

    async def dhcp_server_remove(
        self, creds: DeviceCredentials, server_id: str
    ) -> None:
        await self._call(creds, "/ip/dhcp-server/remove", **{".id": server_id})

    # ---------------- DHCP networks ----------------

    async def dhcp_networks_list(
        self, creds: DeviceCredentials
    ) -> list[DhcpNetwork]:
        rows = await self._call(creds, "/ip/dhcp-server/network/print")
        # RouterOS returns dns-server / ntp-server as a comma-joined
        # string in older versions, but newer 7.x can serialise them
        # as a Python list through librouteros. The pydantic public
        # schema only knows about `str | None`, so coerce here.
        return [
            DhcpNetwork(
                id=r.get(".id"),
                address=str(r.get("address", "")),
                gateway=_csv_or_none(r.get("gateway")),
                netmask=_csv_or_none(r.get("netmask")),
                dns_servers=_csv_or_none(r.get("dns-server")),
                ntp_servers=_csv_or_none(r.get("ntp-server")),
                domain=r.get("domain"),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    async def dhcp_network_add(
        self, creds: DeviceCredentials, network: DhcpNetwork
    ) -> str:
        params: dict[str, Any] = {"address": network.address}
        for k, v in {
            "gateway": network.gateway,
            "netmask": network.netmask,
            "dns-server": network.dns_servers,
            "ntp-server": network.ntp_servers,
            "domain": network.domain,
            "comment": network.comment,
        }.items():
            if v is not None:
                params[k] = v
        rows = await self._call(creds, "/ip/dhcp-server/network/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def dhcp_network_update(
        self, creds: DeviceCredentials, network_id: str, network: DhcpNetwork
    ) -> None:
        params: dict[str, Any] = {".id": network_id}
        for k, v in {
            "address": network.address,
            "gateway": network.gateway,
            "netmask": network.netmask,
            "dns-server": network.dns_servers,
            "ntp-server": network.ntp_servers,
            "domain": network.domain,
            "comment": network.comment,
        }.items():
            if v is not None:
                params[k] = v
        await self._call(creds, "/ip/dhcp-server/network/set", **params)

    async def dhcp_network_remove(
        self, creds: DeviceCredentials, network_id: str
    ) -> None:
        await self._call(
            creds, "/ip/dhcp-server/network/remove", **{".id": network_id}
        )

    # ============== Firewall / NAT ==============

    async def firewall_nat_list(self, creds: DeviceCredentials) -> list[NatRule]:
        rows = await self._call(creds, "/ip/firewall/nat/print")
        return [
            NatRule(
                id=r.get(".id"),
                chain=str(r.get("chain", "")),
                action=str(r.get("action", "")),
                src_address=_to_str(r.get("src-address")),
                dst_address=_to_str(r.get("dst-address")),
                dst_port=_to_str(r.get("dst-port")),
                protocol=_to_str(r.get("protocol")),
                to_addresses=_to_str(r.get("to-addresses")),
                to_ports=_to_str(r.get("to-ports")),
                in_interface=_to_str(r.get("in-interface")),
                out_interface=_to_str(r.get("out-interface")),
                log=_to_bool(r.get("log")),
                log_prefix=_to_str(r.get("log-prefix")),
                bytes_count=_int_or_none(r.get("bytes")),
                packets_count=_int_or_none(r.get("packets")),
                disabled=_to_bool(r.get("disabled")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    async def firewall_nat_set(
        self,
        creds: DeviceCredentials,
        rule_id: str,
        *,
        disabled: bool | None = None,
        log: bool | None = None,
        log_prefix: str | None = None,
    ) -> None:
        params: dict[str, Any] = {".id": rule_id}
        if disabled is not None:
            params["disabled"] = "yes" if disabled else "no"
        if log is not None:
            params["log"] = "yes" if log else "no"
        if log_prefix is not None:
            params["log-prefix"] = log_prefix
        await self._call(creds, "/ip/firewall/nat/set", **params)

    async def firewall_nat_reset_counters(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None:
        await self._call(
            creds, "/ip/firewall/nat/reset-counters", **{".id": rule_id}
        )

    async def interface_reset_counters(
        self, creds: DeviceCredentials, interface_name: str
    ) -> None:
        await self._call(
            creds, "/interface/reset-counters", numbers=interface_name
        )

    async def firewall_nat_add(self, creds: DeviceCredentials, rule: NatRule) -> str:
        params: dict[str, Any] = {"chain": rule.chain, "action": rule.action}
        for k, v in {
            "src-address": rule.src_address,
            "dst-address": rule.dst_address,
            "dst-port": rule.dst_port,
            "protocol": rule.protocol,
            "to-addresses": rule.to_addresses,
            "to-ports": rule.to_ports,
            "in-interface": rule.in_interface,
            "out-interface": rule.out_interface,
            "comment": rule.comment,
        }.items():
            if v is not None:
                params[k] = v

        rows = await self._call(creds, "/ip/firewall/nat/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def firewall_nat_remove(self, creds: DeviceCredentials, rule_id: str) -> None:
        await self._call(creds, "/ip/firewall/nat/remove", **{".id": rule_id})

    # ============== Firewall filter ==============

    async def firewall_filter_list(self, creds: DeviceCredentials) -> list[FilterRule]:
        rows = await self._call(creds, "/ip/firewall/filter/print")
        return [_row_to_filter_rule(r) for r in rows]

    async def firewall_filter_add(
        self, creds: DeviceCredentials, rule: FilterRule
    ) -> str:
        params: dict[str, Any] = {"chain": rule.chain, "action": rule.action}
        for k, v in {
            "src-address": rule.src_address,
            "dst-address": rule.dst_address,
            "src-address-list": rule.src_address_list,
            "dst-address-list": rule.dst_address_list,
            "protocol": rule.protocol,
            "src-port": rule.src_port,
            "dst-port": rule.dst_port,
            "in-interface": rule.in_interface,
            "out-interface": rule.out_interface,
            "connection-state": rule.connection_state,
            "log-prefix": rule.log_prefix,
            "comment": rule.comment,
        }.items():
            if v is not None:
                params[k] = v
        if rule.log:
            params["log"] = "yes"
        if rule.disabled:
            params["disabled"] = "yes"
        rows = await self._call(creds, "/ip/firewall/filter/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def firewall_filter_set(
        self,
        creds: DeviceCredentials,
        rule_id: str,
        *,
        disabled: bool | None = None,
        log: bool | None = None,
        log_prefix: str | None = None,
    ) -> None:
        params: dict[str, Any] = {".id": rule_id}
        if disabled is not None:
            params["disabled"] = "yes" if disabled else "no"
        if log is not None:
            params["log"] = "yes" if log else "no"
        if log_prefix is not None:
            params["log-prefix"] = log_prefix
        await self._call(creds, "/ip/firewall/filter/set", **params)

    async def firewall_filter_reset_counters(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None:
        await self._call(
            creds, "/ip/firewall/filter/reset-counters", **{".id": rule_id}
        )

    async def firewall_filter_remove(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None:
        await self._call(creds, "/ip/firewall/filter/remove", **{".id": rule_id})

    async def firewall_filter_move(
        self,
        creds: DeviceCredentials,
        rule_id: str,
        *,
        before_id: str | None = None,
    ) -> None:
        # RouterOS' /move takes numbers=<src> destination=<dst>; the
        # source ends up immediately before destination. Omitting
        # destination pushes the rule to the bottom of the chain.
        params: dict[str, Any] = {"numbers": rule_id}
        if before_id is not None:
            params["destination"] = before_id
        await self._call(creds, "/ip/firewall/filter/move", **params)

    async def firewall_address_list_add(
        self,
        creds: DeviceCredentials,
        *,
        list_name: str,
        address: str,
        comment: str | None = None,
        timeout: str | None = None,
    ) -> str:
        params: dict[str, Any] = {"list": list_name, "address": address}
        if comment is not None:
            params["comment"] = comment
        if timeout is not None:
            # RouterOS expects values like "1d", "12h", "30m", "1w".
            params["timeout"] = timeout
        rows = await self._call(creds, "/ip/firewall/address-list/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    # ============== IP routes ==============

    async def ip_routes_list(self, creds: DeviceCredentials) -> list[IpRoute]:
        rows = await self._call(creds, "/ip/route/print")
        out: list[IpRoute] = []
        for r in rows:
            dist_raw = r.get("distance")
            try:
                distance = int(dist_raw) if dist_raw is not None else None
            except (TypeError, ValueError):
                distance = None
            out.append(
                IpRoute(
                    id=r.get(".id"),
                    dst_address=str(r.get("dst-address", "")),
                    gateway=r.get("gateway"),
                    distance=distance,
                    routing_table=r.get("routing-table") or r.get("routing-mark") or "main",
                    pref_src=r.get("pref-src"),
                    vrf_interface=r.get("vrf-interface"),
                    active=_to_bool(r.get("active")),
                    dynamic=_to_bool(r.get("dynamic")),
                    static=_to_bool(r.get("static")),
                    disabled=_to_bool(r.get("disabled")),
                    comment=r.get("comment"),
                    raw=r,
                )
            )
        return out

    async def ip_route_add(self, creds: DeviceCredentials, route: IpRoute) -> str:
        params: dict[str, Any] = {"dst-address": route.dst_address}
        for k, v in {
            "gateway": route.gateway,
            "distance": route.distance,
            "routing-table": route.routing_table,
            "pref-src": route.pref_src,
            "comment": route.comment,
        }.items():
            if v is not None:
                params[k] = v
        if route.disabled:
            params["disabled"] = "yes"
        rows = await self._call(creds, "/ip/route/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def ip_route_remove(self, creds: DeviceCredentials, route_id: str) -> None:
        await self._call(creds, "/ip/route/remove", **{".id": route_id})

    # ============== IP addresses ==============

    async def ip_addresses_list(self, creds: DeviceCredentials) -> list[IpAddress]:
        rows = await self._call(creds, "/ip/address/print")
        return [
            IpAddress(
                id=r.get(".id"),
                address=str(r.get("address", "")),
                network=r.get("network"),
                interface=r.get("interface"),
                disabled=_to_bool(r.get("disabled")),
                invalid=_to_bool(r.get("invalid")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    async def interface_list_members(
        self, creds: DeviceCredentials, list_name: str
    ) -> list[str]:
        rows = await self._call(creds, "/interface/list/member/print")
        return [
            str(r.get("interface", ""))
            for r in rows
            if str(r.get("list", "")).lower() == list_name.lower()
            and r.get("interface")
        ]

    async def interface_lists(
        self, creds: DeviceCredentials
    ) -> list[InterfaceList]:
        rows = await self._call(creds, "/interface/list/print")
        return [
            InterfaceList(
                id=r.get(".id"),
                name=str(r.get("name", "")),
                include=_to_str(r.get("include")),
                exclude=_to_str(r.get("exclude")),
                dynamic=_to_bool(r.get("dynamic")),
                builtin=_to_bool(r.get("builtin")),
                comment=_to_str(r.get("comment")),
                raw=r,
            )
            for r in rows
        ]

    async def interface_list_membership(
        self, creds: DeviceCredentials
    ) -> list[InterfaceListMember]:
        """Every (list, interface) pair on the box. Returned ordered
        the same way RouterOS prints them so the UI can group by list
        without a second sort step."""
        rows = await self._call(creds, "/interface/list/member/print")
        return [
            InterfaceListMember(
                id=r.get(".id"),
                list=str(r.get("list", "")),
                interface=str(r.get("interface", "")),
                dynamic=_to_bool(r.get("dynamic")),
                disabled=_to_bool(r.get("disabled")),
                comment=_to_str(r.get("comment")),
                raw=r,
            )
            for r in rows
            if r.get("list") and r.get("interface")
        ]

    async def ip_address_add(
        self,
        creds: DeviceCredentials,
        *,
        address: str,
        interface: str,
        comment: str | None = None,
    ) -> str:
        params: dict[str, Any] = {"address": address, "interface": interface}
        if comment is not None:
            params["comment"] = comment
        rows = await self._call(creds, "/ip/address/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    # ============== ARP ==============

    async def ip_arp_list(self, creds: DeviceCredentials) -> list[ArpEntry]:
        rows = await self._call(creds, "/ip/arp/print")
        return [
            ArpEntry(
                id=r.get(".id"),
                address=str(r.get("address", "")),
                mac_address=r.get("mac-address"),
                interface=r.get("interface"),
                complete=_to_bool(r.get("complete")),
                dynamic=_to_bool(r.get("dynamic")),
                invalid=_to_bool(r.get("invalid")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    # ============== Bridge hosts ==============

    async def bridge_hosts_list(self, creds: DeviceCredentials) -> list[BridgeHost]:
        rows = await self._call(creds, "/interface/bridge/host/print")
        return [
            BridgeHost(
                id=r.get(".id"),
                mac_address=str(r.get("mac-address", "")),
                on_interface=r.get("on-interface"),
                bridge=r.get("bridge"),
                age=r.get("age"),
                dynamic=_to_bool(r.get("dynamic")),
                external=_to_bool(r.get("external")),
                raw=r,
            )
            for r in rows
        ]

    # ============== Neighbours (CDP / LLDP / MNDP) ==============

    async def ip_neighbor_discovery_get(
        self, creds: DeviceCredentials
    ) -> NeighborDiscoverySettings:
        rows = await self._call(creds, "/ip/neighbor/discovery-settings/print")
        r = rows[0] if rows else {}
        return NeighborDiscoverySettings(
            discover_interface_list=_to_str(r.get("discover-interface-list")),
            # RouterOS calls this field `protocol` (singular) but it carries
            # a comma list. Surface as `protocols` to make that obvious.
            protocols=_to_str(r.get("protocol")),
            raw=r,
        )

    async def ip_neighbor_discovery_set(
        self,
        creds: DeviceCredentials,
        *,
        discover_interface_list: str | None = None,
        protocols: str | None = None,
    ) -> None:
        params: dict[str, Any] = {}
        if discover_interface_list is not None:
            params["discover-interface-list"] = discover_interface_list
        if protocols is not None:
            params["protocol"] = protocols
        if not params:
            return
        await self._call(creds, "/ip/neighbor/discovery-settings/set", **params)

    async def ip_neighbors_list(self, creds: DeviceCredentials) -> list[Neighbor]:
        rows = await self._call(creds, "/ip/neighbor/print")
        return [
            Neighbor(
                id=r.get(".id"),
                interface=r.get("interface"),
                address=r.get("address"),
                address6=r.get("address6") or r.get("address-6"),
                mac_address=r.get("mac-address"),
                identity=r.get("identity"),
                platform=r.get("platform"),
                version=r.get("version"),
                board=r.get("board"),
                interface_name=r.get("interface-name"),
                # RouterOS exposes both "discovered-by" (older) and "protocol"
                # (newer) — keep whichever is present.
                discovered_by=r.get("discovered-by") or r.get("protocol"),
                age=r.get("age"),
                uptime=r.get("uptime"),
                raw=r,
            )
            for r in rows
        ]

    # ============== Queues ==============

    async def queue_simple_list(self, creds: DeviceCredentials) -> list[SimpleQueue]:
        rows = await self._call(creds, "/queue/simple/print")
        out: list[SimpleQueue] = []
        for r in rows:
            bytes_str = r.get("bytes")
            bin_, bout = None, None
            if isinstance(bytes_str, str) and "/" in bytes_str:
                parts = bytes_str.split("/")
                if len(parts) == 2:
                    try:
                        bin_, bout = int(parts[0]), int(parts[1])
                    except ValueError:
                        pass
            out.append(
                SimpleQueue(
                    id=r.get(".id"),
                    name=str(r.get("name", "")),
                    target=r.get("target"),
                    max_limit=r.get("max-limit"),
                    burst_limit=r.get("burst-limit"),
                    burst_threshold=r.get("burst-threshold"),
                    burst_time=r.get("burst-time"),
                    parent=r.get("parent"),
                    priority=r.get("priority"),
                    bytes_in=bin_,
                    bytes_out=bout,
                    disabled=_to_bool(r.get("disabled")),
                    comment=r.get("comment"),
                    raw=r,
                )
            )
        return out

    async def queue_simple_add(
        self, creds: DeviceCredentials, queue: SimpleQueue
    ) -> str:
        params: dict[str, Any] = {"name": queue.name}
        for k, v in {
            "target": queue.target,
            "max-limit": queue.max_limit,
            "burst-limit": queue.burst_limit,
            "burst-threshold": queue.burst_threshold,
            "burst-time": queue.burst_time,
            "parent": queue.parent,
            "priority": queue.priority,
            "comment": queue.comment,
        }.items():
            if v is not None:
                params[k] = v
        if queue.disabled:
            params["disabled"] = "yes"
        rows = await self._call(creds, "/queue/simple/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def queue_simple_remove(
        self, creds: DeviceCredentials, queue_id: str
    ) -> None:
        await self._call(creds, "/queue/simple/remove", **{".id": queue_id})

    async def queue_simple_reset_counters(
        self, creds: DeviceCredentials, queue_id: str
    ) -> None:
        await self._call(creds, "/queue/simple/reset-counters", **{".id": queue_id})

    # ============== Interfaces + VLANs ==============

    async def interfaces_list(self, creds: DeviceCredentials) -> list[Interface]:
        rows = await self._call(creds, "/interface/print")

        def _int_or_none(v: Any) -> int | None:
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        return [
            Interface(
                id=r.get(".id"),
                name=str(r.get("name", "")),
                type=str(r.get("type", "")),
                running=_to_bool(r.get("running")),
                disabled=_to_bool(r.get("disabled")),
                mac_address=r.get("mac-address"),
                mtu=_int_or_none(r.get("mtu")),
                actual_mtu=_int_or_none(r.get("actual-mtu")),
                rx_bytes=_int_or_none(r.get("rx-byte")),
                tx_bytes=_int_or_none(r.get("tx-byte")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    async def vlan_list(self, creds: DeviceCredentials) -> list[VlanInterface]:
        rows = await self._call(creds, "/interface/vlan/print")

        def _int_or_zero(v: Any) -> int:
            try:
                return int(v) if v is not None else 0
            except (TypeError, ValueError):
                return 0

        out: list[VlanInterface] = []
        for r in rows:
            mtu_val = r.get("mtu")
            try:
                mtu = int(mtu_val) if mtu_val is not None else None
            except (TypeError, ValueError):
                mtu = None
            out.append(
                VlanInterface(
                    id=r.get(".id"),
                    name=str(r.get("name", "")),
                    interface=str(r.get("interface", "")),
                    vlan_id=_int_or_zero(r.get("vlan-id")),
                    mtu=mtu,
                    disabled=_to_bool(r.get("disabled")),
                    comment=r.get("comment"),
                    raw=r,
                )
            )
        return out

    async def vlan_add(self, creds: DeviceCredentials, vlan: VlanInterface) -> str:
        params: dict[str, Any] = {
            "name": vlan.name,
            "interface": vlan.interface,
            "vlan-id": vlan.vlan_id,
        }
        if vlan.mtu is not None:
            params["mtu"] = vlan.mtu
        if vlan.comment is not None:
            params["comment"] = vlan.comment
        if vlan.disabled:
            params["disabled"] = "yes"
        rows = await self._call(creds, "/interface/vlan/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def vlan_remove(self, creds: DeviceCredentials, vlan_id: str) -> None:
        await self._call(creds, "/interface/vlan/remove", **{".id": vlan_id})

    # ============== NTP ==============

    async def ntp_client_get(self, creds: DeviceCredentials) -> NtpClient:
        rows = await self._call(creds, "/system/ntp/client/print")
        r = rows[0] if rows else {}
        return NtpClient(
            enabled=_to_bool(r.get("enabled")),
            mode=r.get("mode"),
            servers=r.get("server-dns-names") or r.get("servers"),
            primary=r.get("primary-ntp"),
            secondary=r.get("secondary-ntp"),
            raw=r,
        )

    async def ntp_client_set(
        self,
        creds: DeviceCredentials,
        *,
        enabled: bool | None = None,
        mode: str | None = None,
        servers: str | None = None,
        primary: str | None = None,
        secondary: str | None = None,
    ) -> None:
        params: dict[str, Any] = {}
        if enabled is not None:
            params["enabled"] = "yes" if enabled else "no"
        if mode is not None:
            params["mode"] = mode
        if servers is not None:
            # RouterOS 7 uses server-dns-names; we set both for cross-version safety
            params["server-dns-names"] = servers
        if primary is not None:
            params["primary-ntp"] = primary
        if secondary is not None:
            params["secondary-ntp"] = secondary
        await self._call(creds, "/system/ntp/client/set", **params)

    # ============== Firmware ==============

    async def firmware_check_updates(
        self, creds: DeviceCredentials
    ) -> FirmwareInfo:
        """Trigger /system/package/update/check-for-updates then read the result.

        Also pulls /system/routerboard/print so the UI knows if the bootloader
        needs upgrading (the second-stage upgrade after RouterOS update).
        """
        try:
            await self._call(creds, "/system/package/update/check-for-updates")
        except Exception:
            pass  # cached results are still useful

        rows = await self._call(creds, "/system/package/update/print")
        u = rows[0] if rows else {}

        rb_current = None
        rb_available = None
        try:
            rb_rows = await self._call(creds, "/system/routerboard/print")
            rb = rb_rows[0] if rb_rows else {}
            rb_current = rb.get("current-firmware")
            rb_available = rb.get("upgrade-firmware")
        except Exception:
            pass

        return FirmwareInfo(
            current_version=u.get("installed-version"),
            available_version=u.get("latest-version"),
            channel=u.get("channel"),
            routerboard_current=rb_current,
            routerboard_available=rb_available,
            status=u.get("status"),
            raw=u,
        )

    async def firmware_upgrade(self, creds: DeviceCredentials) -> None:
        """RouterOS: /system/package/update/install — downloads + installs +
        reboots. The router will drop the connection mid-call; we suppress
        that and treat it as success.
        """
        try:
            await self._call(creds, "/system/package/update/install")
        except Exception as e:
            # Connection drops on install are normal — RouterOS reboots before
            # the API can ack the command. Re-raise only if it looks like a
            # real refusal (auth, "no update available", etc.).
            msg = str(e).lower()
            if any(s in msg for s in ("no update", "not allowed", "no permission", "auth")):
                raise

    async def firmware_routerboard_upgrade(self, creds: DeviceCredentials) -> None:
        """/system/routerboard/upgrade then /system/reboot. Two-step because
        the bootloader upgrade is applied at next boot."""
        try:
            await self._call(creds, "/system/routerboard/upgrade")
        except Exception as e:
            msg = str(e).lower()
            if any(s in msg for s in ("not allowed", "no permission", "auth")):
                raise
        try:
            await self._call(creds, "/system/reboot")
        except Exception:
            pass  # connection drop on reboot is expected

    # ============== NTP server (router as server) ==============

    async def ntp_server_get(self, creds: DeviceCredentials) -> NtpServer:
        rows = await self._call(creds, "/system/ntp/server/print")
        r = rows[0] if rows else {}
        return NtpServer(
            enabled=_to_bool(r.get("enabled")),
            broadcast=_to_bool(r.get("broadcast")) if "broadcast" in r else None,
            multicast=_to_bool(r.get("multicast")) if "multicast" in r else None,
            manycast=_to_bool(r.get("manycast")) if "manycast" in r else None,
            auth_key=r.get("auth-key"),
            raw=r,
        )

    async def ntp_server_set(
        self,
        creds: DeviceCredentials,
        *,
        enabled: bool | None = None,
        broadcast: bool | None = None,
        multicast: bool | None = None,
        manycast: bool | None = None,
    ) -> None:
        params: dict[str, Any] = {}
        if enabled is not None:
            params["enabled"] = "yes" if enabled else "no"
        if broadcast is not None:
            params["broadcast"] = "yes" if broadcast else "no"
        if multicast is not None:
            params["multicast"] = "yes" if multicast else "no"
        if manycast is not None:
            params["manycast"] = "yes" if manycast else "no"
        await self._call(creds, "/system/ntp/server/set", **params)

    # ============== Clock ==============

    async def clock_get(self, creds: DeviceCredentials) -> DeviceClock:
        rows = await self._call(creds, "/system/clock/print")
        r = rows[0] if rows else {}
        return DeviceClock(
            time=r.get("time"),
            date=r.get("date"),
            time_zone_name=r.get("time-zone-name"),
            time_zone_autodetect=(
                _to_bool(r.get("time-zone-autodetect"))
                if "time-zone-autodetect" in r
                else None
            ),
            gmt_offset=r.get("gmt-offset"),
            dst_active=_to_bool(r.get("dst-active")) if "dst-active" in r else None,
            raw=r,
        )

    async def clock_set(
        self,
        creds: DeviceCredentials,
        *,
        time_zone_name: str | None = None,
        time_zone_autodetect: bool | None = None,
    ) -> None:
        """/system/clock/set time-zone-name=... time-zone-autodetect=...

        RouterOS accepts the IANA tz database name verbatim
        (e.g. "Asia/Tbilisi", "Europe/London", "manual"). When the
        operator picks "manual" they're expected to also disable
        autodetect; we pass through whatever the caller hands us.
        """
        params: dict[str, Any] = {}
        if time_zone_name is not None:
            params["time-zone-name"] = time_zone_name
        if time_zone_autodetect is not None:
            params["time-zone-autodetect"] = "yes" if time_zone_autodetect else "no"
        if not params:
            return
        await self._call(creds, "/system/clock/set", **params)

    # ============== SNMP ==============

    async def snmp_get(self, creds: DeviceCredentials) -> SnmpSettings:
        rows = await self._call(creds, "/snmp/print")
        r = rows[0] if rows else {}
        # librouteros decodes numeric RouterOS values to int (e.g. trap-version=1),
        # but our schema models trap_version as `"1" | "2" | "3"`. Coerce to str.
        raw_tv = r.get("trap-version")
        return SnmpSettings(
            enabled=_to_bool(r.get("enabled")),
            contact=r.get("contact"),
            location=r.get("location"),
            trap_target=r.get("trap-target"),
            trap_version=str(raw_tv) if raw_tv is not None else None,
            engine_id=r.get("engine-id"),
            raw=r,
        )

    async def snmp_set(
        self,
        creds: DeviceCredentials,
        *,
        enabled: bool | None = None,
        contact: str | None = None,
        location: str | None = None,
        trap_target: str | None = None,
        trap_version: str | None = None,
    ) -> None:
        params: dict[str, Any] = {}
        if enabled is not None:
            params["enabled"] = "yes" if enabled else "no"
        if contact is not None:
            params["contact"] = contact
        if location is not None:
            params["location"] = location
        if trap_target is not None:
            params["trap-target"] = trap_target
        if trap_version is not None:
            params["trap-version"] = trap_version
        await self._call(creds, "/snmp/set", **params)

    async def snmp_community_list(self, creds: DeviceCredentials) -> list[SnmpCommunity]:
        rows = await self._call(creds, "/snmp/community/print")
        return [
            SnmpCommunity(
                id=r.get(".id"),
                name=str(r.get("name", "")),
                addresses=r.get("addresses"),
                security=r.get("security"),
                read_access=_to_bool(r.get("read-access")),
                write_access=_to_bool(r.get("write-access")),
                disabled=_to_bool(r.get("disabled")),
                raw=r,
            )
            for r in rows
        ]

    async def snmp_community_add(
        self, creds: DeviceCredentials, community: SnmpCommunity
    ) -> str:
        params: dict[str, Any] = {
            "name": community.name,
            "read-access": "yes" if community.read_access else "no",
            "write-access": "yes" if community.write_access else "no",
        }
        if community.addresses:
            params["addresses"] = community.addresses
        if community.security:
            params["security"] = community.security
        if community.disabled:
            params["disabled"] = "yes"
        rows = await self._call(creds, "/snmp/community/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def snmp_community_remove(
        self, creds: DeviceCredentials, community_id: str
    ) -> None:
        await self._call(creds, "/snmp/community/remove", **{".id": community_id})

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
    ) -> None:
        params: dict[str, Any] = {".id": community_id}
        if name is not None:
            params["name"] = name
        if addresses is not None:
            # RouterOS treats empty string as "any" — feed it through verbatim
            # so the caller can clear the whitelist.
            params["addresses"] = addresses
        if security is not None:
            params["security"] = security
        if read_access is not None:
            params["read-access"] = "yes" if read_access else "no"
        if write_access is not None:
            params["write-access"] = "yes" if write_access else "no"
        if disabled is not None:
            params["disabled"] = "yes" if disabled else "no"
        await self._call(creds, "/snmp/community/set", **params)

    # ============== System log ==============

    async def log_list(
        self,
        creds: DeviceCredentials,
        *,
        topics: str | None = None,
        limit: int = 200,
    ) -> list[LogEntry]:
        rows = await self._call(creds, "/log/print")
        # `topics` is a comma-separated "any-of" filter — historically
        # we compared the whole filter string against each row's
        # topics, which essentially never matched because RouterOS
        # writes rows like "system,info" not "critical,error,warning".
        # Split it into a set and keep any row that mentions at least
        # one of them.
        wanted = (
            {t.strip().lower() for t in topics.split(",") if t.strip()}
            if topics
            else None
        )
        out: list[LogEntry] = []
        for r in rows:
            row_topics = str(r.get("topics", ""))
            if wanted is not None:
                row_set = {t.strip().lower() for t in row_topics.split(",")}
                if wanted.isdisjoint(row_set):
                    continue
            out.append(
                LogEntry(
                    time=str(r.get("time", "")),
                    topics=row_topics,
                    message=str(r.get("message", "")),
                    raw=r,
                )
            )
        # RouterOS' /log/print returns oldest-first, which is the natural
        # terminal-tail order operators are used to (newest at the bottom).
        # Take the LAST `limit` lines so the cap drops old entries instead
        # of fresh ones. The frontend's auto-scroll-to-bottom then lands on
        # the latest line by default.
        return out[-limit:]

    # ============== System / logging rules ==============

    async def system_logging_list(
        self, creds: DeviceCredentials
    ) -> list[LoggingRule]:
        rows = await self._call(creds, "/system/logging/print")
        return [
            LoggingRule(
                id=r.get(".id"),
                topics=str(r.get("topics", "")),
                action=str(r.get("action", "")),
                prefix=_to_str(r.get("prefix")),
                disabled=_to_bool(r.get("disabled")),
                invalid=_to_bool(r.get("invalid")),
                default=_to_bool(r.get("default")),
                raw=r,
            )
            for r in rows
        ]

    async def system_logging_add(
        self,
        creds: DeviceCredentials,
        *,
        topics: str,
        action: str,
        prefix: str | None = None,
        disabled: bool = False,
    ) -> str:
        params: dict[str, Any] = {"topics": topics, "action": action}
        if prefix is not None:
            params["prefix"] = prefix
        if disabled:
            params["disabled"] = "yes"
        rows = await self._call(creds, "/system/logging/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def system_logging_set(
        self,
        creds: DeviceCredentials,
        rule_id: str,
        *,
        topics: str | None = None,
        action: str | None = None,
        prefix: str | None = None,
        disabled: bool | None = None,
    ) -> None:
        params: dict[str, Any] = {".id": rule_id}
        if topics is not None:
            params["topics"] = topics
        if action is not None:
            params["action"] = action
        if prefix is not None:
            params["prefix"] = prefix
        if disabled is not None:
            params["disabled"] = "yes" if disabled else "no"
        await self._call(creds, "/system/logging/set", **params)

    async def system_logging_remove(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None:
        await self._call(creds, "/system/logging/remove", **{".id": rule_id})

    # ============== System / logging actions ==============

    async def system_logging_actions_list(
        self, creds: DeviceCredentials
    ) -> list[LoggingAction]:
        rows = await self._call(creds, "/system/logging/action/print")
        return [
            LoggingAction(
                id=r.get(".id"),
                name=str(r.get("name", "")),
                target=str(r.get("target", "")),
                remote=_to_str(r.get("remote")),
                remote_port=_int_or_none(r.get("remote-port")),
                src_address=_to_str(r.get("src-address")),
                bsd_syslog=_to_bool(r.get("bsd-syslog"))
                if r.get("bsd-syslog") is not None
                else None,
                syslog_facility=_to_str(r.get("syslog-facility")),
                syslog_severity=_to_str(r.get("syslog-severity")),
                memory_lines=_int_or_none(r.get("memory-lines")),
                disk_lines_per_file=_int_or_none(r.get("disk-lines-per-file")),
                disk_file_count=_int_or_none(r.get("disk-file-count")),
                default=_to_bool(r.get("default")),
                raw=r,
            )
            for r in rows
        ]

    async def system_logging_action_add(
        self,
        creds: DeviceCredentials,
        *,
        name: str,
        target: str,
        remote: str | None = None,
        remote_port: int | None = None,
        src_address: str | None = None,
        bsd_syslog: bool | None = None,
        syslog_facility: str | None = None,
        syslog_severity: str | None = None,
        memory_lines: int | None = None,
    ) -> str:
        params: dict[str, Any] = {"name": name, "target": target}
        if remote is not None:
            params["remote"] = remote
        if remote_port is not None:
            params["remote-port"] = remote_port
        if src_address is not None:
            params["src-address"] = src_address
        if bsd_syslog is not None:
            params["bsd-syslog"] = "yes" if bsd_syslog else "no"
        if syslog_facility is not None:
            params["syslog-facility"] = syslog_facility
        if syslog_severity is not None:
            params["syslog-severity"] = syslog_severity
        if memory_lines is not None:
            params["memory-lines"] = memory_lines
        rows = await self._call(creds, "/system/logging/action/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def system_logging_action_remove(
        self, creds: DeviceCredentials, action_id: str
    ) -> None:
        await self._call(
            creds, "/system/logging/action/remove", **{".id": action_id}
        )

    # ============== IP services ==============

    async def ip_services_list(self, creds: DeviceCredentials) -> list[IpService]:
        rows = await self._call(creds, "/ip/service/print")
        out: list[IpService] = []
        for r in rows:
            name = str(r.get("name", ""))
            tls_only = name.endswith("-ssl") or _to_bool(r.get("tls"))
            out.append(
                IpService(
                    name=name,
                    port=int(r.get("port", 0)) if r.get("port") else 0,
                    enabled=not _to_bool(r.get("disabled")),
                    address=r.get("address"),
                    certificate=r.get("certificate") or None,
                    tls_only=tls_only,
                    raw=r,
                )
            )
        return out

    async def ip_service_set(
        self,
        creds: DeviceCredentials,
        name: str,
        *,
        enabled: bool | None = None,
        port: int | None = None,
        address: str | None = None,
    ) -> None:
        # /ip/service has 6-8 rows; cheaper to filter in Python than to
        # wrangle librouteros' Query API across versions.
        rows = await self._call(creds, "/ip/service/print")
        match = next((r for r in rows if r.get("name") == name), None)
        if not match:
            raise ValueError(f"ip service '{name}' not found on device")
        svc_id = match.get(".id")
        if not svc_id:
            raise ValueError(f"ip service '{name}' has no .id")

        params: dict[str, Any] = {".id": svc_id}
        if enabled is not None:
            params["disabled"] = "no" if enabled else "yes"
        if port is not None:
            params["port"] = port
        if address is not None:
            # Empty string clears the whitelist on RouterOS; pass through.
            params["address"] = address

        await self._call(creds, "/ip/service/set", **params)

    # ============== Device users ==============

    async def device_users_list(self, creds: DeviceCredentials) -> list[DeviceUser]:
        rows = await self._call(creds, "/user/print")
        return [
            DeviceUser(
                id=r.get(".id"),
                name=str(r.get("name", "")),
                group=r.get("group"),
                disabled=_to_bool(r.get("disabled")),
                comment=r.get("comment"),
                last_logged_in=r.get("last-logged-in"),
                raw=r,
            )
            for r in rows
        ]

    async def device_user_set_password(
        self, creds: DeviceCredentials, username: str, new_password: str
    ) -> None:
        rows = await self._call(creds, "/user/print", **{"?name": username})
        if not rows:
            raise ValueError(f"user '{username}' not found on device")
        await self._call(
            creds, "/user/set", **{".id": rows[0][".id"], "password": new_password}
        )

    async def device_user_set_disabled(
        self, creds: DeviceCredentials, username: str, disabled: bool
    ) -> None:
        rows = await self._call(creds, "/user/print", **{"?name": username})
        if not rows:
            raise ValueError(f"user '{username}' not found on device")
        await self._call(
            creds,
            "/user/set",
            **{".id": rows[0][".id"], "disabled": "yes" if disabled else "no"},
        )

    # ============== PPP secrets (L2TP / PPTP / SSTP / OVPN) ==============

    async def ppp_secrets_list(self, creds: DeviceCredentials) -> list[PppSecret]:
        rows = await self._call(creds, "/ppp/secret/print")
        return [_row_to_ppp_secret(r) for r in rows]

    async def ppp_secret_add(
        self, creds: DeviceCredentials, secret: PppSecret, password: str
    ) -> str:
        params: dict[str, Any] = {
            "name": secret.name,
            "service": secret.service,
            "password": password,
        }
        for k, v in {
            "profile": secret.profile,
            "local-address": secret.local_address,
            "remote-address": secret.remote_address,
            "comment": secret.comment,
        }.items():
            if v is not None:
                params[k] = v
        rows = await self._call(creds, "/ppp/secret/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def ppp_secret_set_password(
        self, creds: DeviceCredentials, secret_id: str, new_password: str
    ) -> None:
        await self._call(creds, "/ppp/secret/set", **{".id": secret_id, "password": new_password})

    async def ppp_secret_remove(self, creds: DeviceCredentials, secret_id: str) -> None:
        await self._call(creds, "/ppp/secret/remove", **{".id": secret_id})

    async def ppp_secret_reveal_password(
        self, creds: DeviceCredentials, secret_id: str
    ) -> str:
        # RouterOS exposes the password field directly via the API; the UI just hides it.
        rows = await self._call(creds, "/ppp/secret/print", **{"?.id": secret_id})
        if not rows:
            raise ValueError("ppp secret not found")
        return str(rows[0].get("password", ""))

    # ============== WireGuard ==============

    async def wireguard_interfaces_list(
        self, creds: DeviceCredentials
    ) -> list[WireguardInterface]:
        rows = await self._call(creds, "/interface/wireguard/print")
        return [
            WireguardInterface(
                id=r.get(".id"),
                name=str(r.get("name", "")),
                listen_port=int(r["listen-port"]) if r.get("listen-port") else None,
                # private_key never returned here — caller must use reveal endpoint
                public_key=r.get("public-key"),
                mtu=int(r["mtu"]) if r.get("mtu") else None,
                disabled=_to_bool(r.get("disabled")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    async def wireguard_interface_add(
        self, creds: DeviceCredentials, iface: WireguardInterface
    ) -> str:
        params: dict[str, Any] = {"name": iface.name}
        if iface.listen_port is not None:
            params["listen-port"] = iface.listen_port
        if iface.private_key:
            params["private-key"] = iface.private_key
        if iface.mtu is not None:
            params["mtu"] = iface.mtu
        if iface.comment is not None:
            params["comment"] = iface.comment
        rows = await self._call(creds, "/interface/wireguard/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def wireguard_interface_remove(
        self, creds: DeviceCredentials, iface_id: str
    ) -> None:
        await self._call(creds, "/interface/wireguard/remove", **{".id": iface_id})

    async def wireguard_peers_list(
        self, creds: DeviceCredentials, *, interface: str | None = None
    ) -> list[WireguardPeer]:
        params: dict[str, Any] = {}
        if interface:
            params["?interface"] = interface
        rows = await self._call(creds, "/interface/wireguard/peers/print", **params)
        out: list[WireguardPeer] = []
        for r in rows:
            try:
                out.append(
                    WireguardPeer(
                        id=r.get(".id"),
                        interface=str(r.get("interface", "")),
                        public_key=_csv_or_none(r.get("public-key")),
                        # preshared_key is masked by RouterOS — use the
                        # NetFleet-side cache (wg_peer_secrets) via the
                        # reveal endpoint.
                        allowed_address=_csv_or_none(r.get("allowed-address")),
                        endpoint_address=_to_str(r.get("endpoint-address")),
                        endpoint_port=_int_or_none(r.get("endpoint-port")),
                        # RouterOS returns this as "25" or "30s" or "1m"
                        # depending on version; coerce loosely so peers
                        # created outside NetFleet still load.
                        persistent_keepalive=_duration_to_seconds(
                            r.get("persistent-keepalive")
                        ),
                        disabled=_to_bool(r.get("disabled")),
                        comment=r.get("comment"),
                        raw=r,
                    )
                )
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "mikrotik.wg_peer.row_invalid",
                    host=creds.host,
                    error=str(e),
                    row=r,
                )
        return out

    async def wireguard_peer_add(
        self, creds: DeviceCredentials, peer: WireguardPeer
    ) -> str:
        params: dict[str, Any] = {"interface": peer.interface}
        for k, v in {
            "public-key": peer.public_key,
            "preshared-key": peer.preshared_key,
            "allowed-address": peer.allowed_address,
            "endpoint-address": peer.endpoint_address,
            "endpoint-port": peer.endpoint_port,
            "persistent-keepalive": peer.persistent_keepalive,
            "comment": peer.comment,
        }.items():
            if v is not None:
                params[k] = v
        rows = await self._call(creds, "/interface/wireguard/peers/add", **params)
        return str(rows[0].get("ret", "")) if rows else ""

    async def wireguard_peer_remove(self, creds: DeviceCredentials, peer_id: str) -> None:
        await self._call(creds, "/interface/wireguard/peers/remove", **{".id": peer_id})

    async def wireguard_peer_reveal_keys(
        self, creds: DeviceCredentials, peer_id: str
    ) -> dict[str, str | None]:
        rows = await self._call(creds, "/interface/wireguard/peers/print", **{"?.id": peer_id})
        if not rows:
            raise ValueError("wireguard peer not found")
        r = rows[0]
        return {
            "public_key": r.get("public-key"),
            "preshared_key": r.get("preshared-key"),
        }

    # ============== Backup ==============

    async def system_backup(
        self, creds: DeviceCredentials, *, ssh_port: int = 22
    ) -> BackupArtifact:
        """Trigger /system/backup/save (binary) + /export (script), then SFTP
        both files off the device.

        SSH/SFTP must be enabled on the router. The librouteros API does not
        expose binary file download, so this is the only way to actually
        retrieve the .backup blob — without it the saved file just sits on
        the device's /file root.
        """
        from librouteros.exceptions import TrapError

        ts = datetime.now(UTC)
        name = f"netfleet-{ts.strftime('%Y%m%d-%H%M%S')}"
        backup_filename = f"{name}.backup"
        rsc_filename = f"{name}.rsc"

        # 1) Trigger the binary backup. RouterOS returns once the file is on disk.
        try:
            await self._call(creds, "/system/backup/save", name=name)
        except TrapError as e:
            raise RuntimeError(f"backup save failed: {e}") from e

        # 2) Trigger /export — script-format dump. Best-effort: some perms
        # / RouterOS versions don't let you /export to file. We log and
        # continue with an empty .rsc rather than failing the whole backup.
        try:
            await self._call(creds, "/export", file=name)
        except Exception as e:
            log.info("mikrotik.export_skipped", host=creds.host, error=str(e))

        # 3) SFTP-pull both files. The .backup is mandatory — if SFTP fails
        # here, the whole backup is reported as failed (no point persisting
        # a row that references a file that never made it off the device).
        try:
            backup_bytes = await asyncio.to_thread(
                _sftp_get,
                host=creds.host,
                port=ssh_port,
                username=creds.username,
                password=creds.password or "",
                remote_name=backup_filename,
            )
        except Exception as e:
            raise RuntimeError(
                f"failed to pull {backup_filename} via SFTP on "
                f"{creds.host}:{ssh_port} — {e}. "
                "On the router, verify (1) /ip/service set ssh disabled=no, "
                "(2) the ssh service has no address whitelist OR includes "
                "NetFleet's outgoing IP, and (3) the input firewall chain "
                "accepts TCP/{port} from NetFleet's source. "
                "If SSH actually listens on a different port, edit the "
                "device's SSH port (defaults to 22).".format(port=ssh_port)
            ) from e

        rsc_text = ""
        try:
            rsc_bytes = await asyncio.to_thread(
                _sftp_get,
                host=creds.host,
                port=ssh_port,
                username=creds.username,
                password=creds.password or "",
                remote_name=rsc_filename,
            )
            rsc_text = rsc_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            log.info("mikrotik.rsc_pull_skipped", host=creds.host, error=str(e))

        # 4) Best-effort cleanup of the files we created on the device.
        for fname in (backup_filename, rsc_filename):
            try:
                await asyncio.to_thread(
                    _sftp_remove,
                    host=creds.host,
                    port=ssh_port,
                    username=creds.username,
                    password=creds.password or "",
                    remote_name=fname,
                )
            except Exception:
                pass

        return BackupArtifact(
            backup_bytes=backup_bytes, rsc_text=rsc_text, timestamp_iso=ts.isoformat()
        )

    async def system_restore(
        self,
        creds: DeviceCredentials,
        *,
        local_backup_path: Path,
        ssh_port: int = 22,
    ) -> None:
        """Upload .backup over SFTP, trigger /system/backup/load. Device reboots."""
        if not local_backup_path.is_file():
            raise RuntimeError(f"local backup not found: {local_backup_path}")

        remote_filename = local_backup_path.name
        if not remote_filename.endswith(".backup"):
            raise RuntimeError("backup file must have a .backup extension")
        name_only = remote_filename.removesuffix(".backup")

        # SSH/SFTP upload is blocking + uses a separate library — push it to a thread.
        await asyncio.to_thread(
            _sftp_put,
            host=creds.host,
            port=ssh_port,
            username=creds.username,
            password=creds.password or "",
            local_path=str(local_backup_path),
            remote_name=remote_filename,
        )

        # Fire the load command. The device starts rebooting almost immediately —
        # the API connection drops mid-reply, which is expected. Wrap it in a
        # short timeout so we don't hang on the closing socket.
        try:
            await asyncio.wait_for(
                self._call(creds, "/system/backup/load", name=name_only),
                timeout=8.0,
            )
        except (TimeoutError, OSError, Exception) as e:  # noqa: BLE001
            log.info(
                "mikrotik.backup_load_dispatched",
                host=creds.host,
                name=name_only,
                drop_reason=type(e).__name__,
            )

    # ============== transport ==============

    async def _call(
        self, creds: DeviceCredentials, path: str, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._call_sync, creds, path, kwargs)

    @staticmethod
    def _call_sync(
        creds: DeviceCredentials, path: str, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        from librouteros import connect

        conn = connect(
            host=creds.host,
            port=creds.port,
            username=creds.username,
            password=creds.password or "",
            timeout=10,
        )
        try:
            cmd_parts = path.strip("/").split("/")
            verb = cmd_parts[-1]
            cmd = conn.path(*cmd_parts[:-1])
            if verb == "print":
                # `print` filters arrive as keys prefixed with "?". librouteros'
                # Path.select() is COLUMN projection, not row filter — using it
                # for filtering silently returned the wrong row's .id and broke
                # every set-by-name operation. Filter in Python instead; the
                # tables we query (/ip/service, /user, /file, /ppp/secret) are
                # all small enough for that to be free.
                rows = list(cmd)
                filters = {k[1:]: v for k, v in params.items() if k.startswith("?")}
                if filters:
                    rows = [
                        r for r in rows
                        if all(str(r.get(f)) == str(v) for f, v in filters.items())
                    ]
                return rows
            # librouteros 4.x's Path only exposes add/remove/update/select directly,
            # so `cmd.save(...)` / `cmd.export(...)` / `cmd.set(...)` all blow up
            # with AttributeError. The lower-level `Path.__call__(verb, **kwargs)`
            # works for every RouterOS API verb and always returns dicts, so
            # callers reading `rows[0]["ret"]` keep working too.
            return list(cmd(verb, **params))
        finally:
            conn.close()


# ---------------- helpers ----------------


def _sftp_put(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    local_path: str,
    remote_name: str,
) -> None:
    """Blocking SFTP upload — must be called via asyncio.to_thread.

    Files are dropped at the root of RouterOS's `/file` namespace (no subdirs
    are supported there), so `remote_name` is just a basename like
    ``netfleet-20260527-153012.backup``.
    """
    with _sftp_session(host, port, username, password) as sftp:
        sftp.put(local_path, remote_name)


def _sftp_get(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    remote_name: str,
) -> bytes:
    """Blocking SFTP download — must be called via asyncio.to_thread.

    Returns the binary contents of `remote_name` from the device's `/file`
    root. Used for pulling /system/backup/save artefacts (binary .backup)
    and /export output (.rsc) off the device.

    RouterOS occasionally hasn't flushed the file by the time the API
    returns from /system/backup/save; retry briefly on file-not-found.
    """
    import io
    import time

    with _sftp_session(host, port, username, password) as sftp:
        last_err: Exception | None = None
        for attempt in range(5):
            try:
                buf = io.BytesIO()
                sftp.getfo(remote_name, buf)
                return buf.getvalue()
            except FileNotFoundError as e:
                last_err = e
                time.sleep(0.5 * (attempt + 1))  # 0.5s, 1.0s, 1.5s, 2.0s, 2.5s
        assert last_err is not None
        raise last_err


def _sftp_remove(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    remote_name: str,
) -> None:
    """Blocking SFTP remove — must be called via asyncio.to_thread."""
    with _sftp_session(host, port, username, password) as sftp:
        try:
            sftp.remove(remote_name)
        except FileNotFoundError:
            pass


@contextmanager
def _sftp_session(host: str, port: int, username: str, password: str):
    """Open an SFTP session as a context manager. Closes both SFTP and the
    underlying SSH transport cleanly even on exceptions.

    RouterOS — especially 6.x and stripped-down 7.x builds — still uses
    legacy SSH key + KEX algorithms (ssh-rsa with SHA-1, ssh-dss,
    diffie-hellman-group1/14-sha1). Modern paramiko disables most of those
    by default, producing an opaque "no matching host key type" failure.
    We re-enable them here. The connection is still encrypted; we're only
    relaxing the algorithm whitelist.
    """
    import paramiko  # imported lazily so the rest of the driver still loads on hosts without it

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        timeout=15,
        allow_agent=False,
        look_for_keys=False,
        # Tell paramiko NOT to disable any algorithm. The default disables
        # SHA-1-based variants that RouterOS still depends on.
        disabled_algorithms={"pubkeys": [], "keys": [], "kex": []},
    )
    try:
        sftp = client.open_sftp()
        try:
            yield sftp
        finally:
            sftp.close()
    finally:
        client.close()


def _row_to_filter_rule(r: dict[str, Any]) -> FilterRule:
    # RouterOS hands back port-shaped fields as `int` when the rule contains a
    # single numeric port (e.g. `dst-port=3478`) and as `str` when it's a range
    # or comma list (`80,443` / `1024-65535`). FilterRule's schema is `str | None`
    # everywhere, so coerce here rather than at every caller.
    return FilterRule(
        id=r.get(".id"),
        chain=str(r.get("chain", "")),
        action=str(r.get("action", "")),
        src_address=_to_str(r.get("src-address")),
        dst_address=_to_str(r.get("dst-address")),
        src_address_list=_to_str(r.get("src-address-list")),
        dst_address_list=_to_str(r.get("dst-address-list")),
        protocol=_to_str(r.get("protocol")),
        src_port=_to_str(r.get("src-port")),
        dst_port=_to_str(r.get("dst-port")),
        in_interface=_to_str(r.get("in-interface")),
        out_interface=_to_str(r.get("out-interface")),
        connection_state=_to_str(r.get("connection-state")),
        log=_to_bool(r.get("log")),
        log_prefix=_to_str(r.get("log-prefix")),
        bytes_count=_int_or_none(r.get("bytes")),
        packets_count=_int_or_none(r.get("packets")),
        disabled=_to_bool(r.get("disabled")),
        comment=_to_str(r.get("comment")),
        raw=r,
    )


def _row_to_ppp_secret(r: dict[str, Any]) -> PppSecret:
    return PppSecret(
        id=r.get(".id"),
        name=str(r.get("name", "")),
        service=str(r.get("service", "any")),
        profile=r.get("profile"),
        local_address=r.get("local-address"),
        remote_address=r.get("remote-address"),
        disabled=_to_bool(r.get("disabled")),
        comment=r.get("comment"),
        raw=r,
    )


def _to_bool(v: Any) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in ("true", "yes", "1")


def _to_str(v: Any) -> str | None:
    """Defensive str coerce. librouteros occasionally returns int for fields
    RouterOS prints as numbers — port, mtu-like — but our public schemas
    declare them as `str | None`. Treat empty string as None to keep the
    "field unset" path consistent on the wire."""
    if v is None:
        return None
    s = str(v)
    return s if s != "" else None


def _csv_or_none(v: Any) -> str | None:
    """RouterOS can serialise multi-valued fields (dns-server, ntp-server,
    gateway with multiple gateways, …) as either a comma-joined string
    or a Python list, depending on RouterOS version + librouteros build.
    Public schemas type these as `str | None`, so collapse list → CSV
    here so pydantic validation doesn't trip and return 500 for a
    perfectly fine row."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        out = ",".join(str(x) for x in v if x is not None and str(x) != "")
        return out or None
    s = str(v)
    return s if s != "" else None


def _int_or_none(v: Any) -> int | None:
    """Loose int coerce. Returns None for missing, empty, or junk values.
    Used for RouterOS port fields that occasionally come back as strings
    with junk attached (no separator) on certain versions."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(str(v).strip().split()[0])
        except (IndexError, ValueError):
            return None


def _duration_to_seconds(v: Any) -> int | None:
    """RouterOS prints durations as e.g. ``"25"``, ``"30s"``, ``"1m"``,
    ``"1h30m"``. Convert any of those to integer seconds. None / empty
    / unparseable returns None so the field stays "unset" rather than
    surfacing a 500."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    units = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
    total = 0
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
            continue
        if ch in units and num:
            total += int(num) * units[ch]
            num = ""
        else:
            # Unknown character — bail and let the caller see None.
            return None
    if num:
        # Trailing bare number with no unit — assume seconds.
        total += int(num)
    return total or None


def _parse_uptime(s: str) -> int | None:
    if not s:
        return None
    units = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
    total = 0
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        elif ch in units and num:
            total += int(num) * units[ch]
            num = ""
        else:
            return None
    return total or None


def _pct_used(free: Any, total: Any) -> float | None:
    try:
        f, t = int(free), int(total)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    return round((1 - f / t) * 100, 1)
