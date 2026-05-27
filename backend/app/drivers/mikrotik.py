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
    FilterRule,
    FirmwareInfo,
    Interface,
    IpAddress,
    IpRoute,
    IpService,
    LogEntry,
    NatRule,
    Neighbor,
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
        return SystemInfo(
            identity=str(identity),
            model=r.get("board-name"),
            firmware=r.get("version"),
            uptime_seconds=_parse_uptime(r.get("uptime", "")),
            cpu_load_pct=float(r.get("cpu-load", 0)) if r.get("cpu-load") else None,
            memory_used_pct=_pct_used(r.get("free-memory"), r.get("total-memory")),
            raw={**r, **(identity_rows[0] if identity_rows else {})},
        )

    # ============== DHCP ==============

    async def dhcp_leases(self, creds: DeviceCredentials) -> list[DhcpLease]:
        rows = await self._call(creds, "/ip/dhcp-server/lease/print")
        return [
            DhcpLease(
                address=str(r.get("address", "")),
                mac_address=str(r.get("mac-address", "")),
                host_name=r.get("host-name"),
                client_id=r.get("client-id"),
                status=r.get("status"),
                server=r.get("server"),
                expires_at_iso=r.get("expires-after"),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

    # ============== Firewall / NAT ==============

    async def firewall_nat_list(self, creds: DeviceCredentials) -> list[NatRule]:
        rows = await self._call(creds, "/ip/firewall/nat/print")
        return [
            NatRule(
                id=r.get(".id"),
                chain=str(r.get("chain", "")),
                action=str(r.get("action", "")),
                src_address=r.get("src-address"),
                dst_address=r.get("dst-address"),
                dst_port=r.get("dst-port"),
                protocol=r.get("protocol"),
                to_addresses=r.get("to-addresses"),
                to_ports=r.get("to-ports"),
                in_interface=r.get("in-interface"),
                out_interface=r.get("out-interface"),
                disabled=_to_bool(r.get("disabled")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

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
        self, creds: DeviceCredentials, rule_id: str, *, disabled: bool | None = None
    ) -> None:
        params: dict[str, Any] = {".id": rule_id}
        if disabled is not None:
            params["disabled"] = "yes" if disabled else "no"
        await self._call(creds, "/ip/firewall/filter/set", **params)

    async def firewall_filter_remove(
        self, creds: DeviceCredentials, rule_id: str
    ) -> None:
        await self._call(creds, "/ip/firewall/filter/remove", **{".id": rule_id})

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

    # ============== System log ==============

    async def log_list(
        self,
        creds: DeviceCredentials,
        *,
        topics: str | None = None,
        limit: int = 200,
    ) -> list[LogEntry]:
        rows = await self._call(creds, "/log/print")
        out: list[LogEntry] = []
        for r in rows:
            row_topics = str(r.get("topics", ""))
            if topics and topics.lower() not in row_topics.lower():
                continue
            out.append(
                LogEntry(
                    time=str(r.get("time", "")),
                    topics=row_topics,
                    message=str(r.get("message", "")),
                    raw=r,
                )
            )
        # RouterOS log is oldest-first; we want newest-first, capped.
        out.reverse()
        return out[:limit]

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
        return [
            WireguardPeer(
                id=r.get(".id"),
                interface=str(r.get("interface", "")),
                public_key=r.get("public-key"),
                # preshared_key never returned — use reveal endpoint
                allowed_address=r.get("allowed-address"),
                endpoint_address=r.get("endpoint-address"),
                endpoint_port=int(r["endpoint-port"]) if r.get("endpoint-port") else None,
                persistent_keepalive=(
                    int(r["persistent-keepalive"]) if r.get("persistent-keepalive") else None
                ),
                disabled=_to_bool(r.get("disabled")),
                comment=r.get("comment"),
                raw=r,
            )
            for r in rows
        ]

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
                f"failed to pull {backup_filename} via SFTP — "
                f"check that SSH is enabled and reachable from NetFleet: {e}"
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
    """
    import io

    with _sftp_session(host, port, username, password) as sftp:
        buf = io.BytesIO()
        sftp.getfo(remote_name, buf)
        return buf.getvalue()


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
    underlying SSH transport cleanly even on exceptions."""
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
    return FilterRule(
        id=r.get(".id"),
        chain=str(r.get("chain", "")),
        action=str(r.get("action", "")),
        src_address=r.get("src-address"),
        dst_address=r.get("dst-address"),
        src_address_list=r.get("src-address-list"),
        dst_address_list=r.get("dst-address-list"),
        protocol=r.get("protocol"),
        src_port=r.get("src-port"),
        dst_port=r.get("dst-port"),
        in_interface=r.get("in-interface"),
        out_interface=r.get("out-interface"),
        connection_state=r.get("connection-state"),
        log=_to_bool(r.get("log")),
        log_prefix=r.get("log-prefix"),
        disabled=_to_bool(r.get("disabled")),
        comment=r.get("comment"),
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
