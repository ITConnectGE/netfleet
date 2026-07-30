"""Linux vendor driver — agentless, over SSH.

Nothing is installed on the managed host: every call shells out over SSH
and parses the result. Where a modern tool emits JSON we use it (`ip -j`,
`systemctl -o json`) rather than scraping human-readable output, because
those formats are stable contracts and column layouts are not.

Distro differences are handled by detecting `os_family` from
`/etc/os-release` and branching on it in the few places it matters
(packages, service names). Everything in this module — the read-only core
— is identical across distros, so there is deliberately no per-family
subclass: one driver, a small command table where it is actually needed.

Only a subset of `Capability` is declared. The UI hides the rest, which is
how a Linux host and a RouterOS device coexist in one device list without
either showing sections that make no sense for it.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.drivers import ssh_transport as ssh
from app.drivers.base import (
    ArpEntry,
    Capability,
    DeviceCredentials,
    Interface,
    IpAddress,
    IpRoute,
    SystemInfo,
)

log = structlog.get_logger(__name__)


# /etc/os-release ID and ID_LIKE values mapped onto the families we branch
# on. Anything unrecognised becomes "unknown", which keeps system_info
# working while the family-specific sections stay unavailable.
_OS_FAMILY_BY_ID = {
    "debian": "debian",
    "ubuntu": "debian",
    "linuxmint": "debian",
    "pop": "debian",
    "raspbian": "debian",
    "rhel": "rhel",
    "centos": "rhel",
    "rocky": "rhel",
    "almalinux": "rhel",
    "fedora": "rhel",
    "ol": "rhel",
    "alpine": "alpine",
    "opensuse": "suse",
    "opensuse-leap": "suse",
    "opensuse-tumbleweed": "suse",
    "sles": "suse",
}


def _parse_os_release(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _os_family_from_release(fields: dict[str, str]) -> str:
    ident = (fields.get("ID") or "").lower()
    if ident in _OS_FAMILY_BY_ID:
        return _OS_FAMILY_BY_ID[ident]
    # ID_LIKE is a space-separated list of ancestors — a derivative we have
    # never heard of usually names one we have.
    for like in (fields.get("ID_LIKE") or "").lower().split():
        if like in _OS_FAMILY_BY_ID:
            return _OS_FAMILY_BY_ID[like]
    return "unknown"


def _json_or_empty(result: ssh.CommandResult, what: str) -> list[dict[str, Any]]:
    """Parse a JSON array from `ip -j`. An empty body is legitimate — `ip
    -j addr` prints nothing at all when there is nothing to report."""
    if not result.ok:
        raise ssh.SshError(
            f"{what} failed: {(result.stderr or result.stdout).strip()[:200]}"
        )
    body = result.stdout.strip()
    if not body:
        return []
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise ssh.SshError(f"{what} returned output that is not JSON: {e}") from e
    return parsed if isinstance(parsed, list) else []


def _first_line(result: ssh.CommandResult) -> str | None:
    if not result.ok:
        return None
    line = result.stdout.strip().splitlines()
    return line[0].strip() if line else None


class LinuxDriver:
    """Agentless Linux management over SSH."""

    vendor = "linux"
    display_name = "Linux (SSH)"

    capabilities: set[Capability] = {
        Capability.SYSTEM_INFO,
        Capability.SYSTEM_REBOOT,
        Capability.INTERFACE_LIST,
        Capability.IP_ADDRESS,
        Capability.IP_ROUTE,
        Capability.IP_NEIGHBOR,
        Capability.TOOL_PING,
        Capability.TOOL_TRACEROUTE,
    }

    # ------------------------------------------------------------- core

    async def test_connection(self, creds: DeviceCredentials) -> bool:
        batch = await ssh.probe(creds)
        return batch.results[0].ok

    async def system_info(self, creds: DeviceCredentials) -> SystemInfo:
        # One connection, one batch. Every value here is a tiny read, so
        # the round-trip cost dominates and batching is what makes the
        # device page load in one blink rather than eight.
        cmds = [
            ssh.Command(argv=["cat", "/etc/os-release"], timeout=10),
            ssh.Command(argv=["uname", "-r"], timeout=10),
            ssh.Command(argv=["hostname", "-f"], timeout=10),
            ssh.Command(argv=["cat", "/proc/uptime"], timeout=10),
            ssh.Command(argv=["cat", "/proc/loadavg"], timeout=10),
            ssh.Command(argv=["cat", "/proc/meminfo"], timeout=10),
            ssh.Command(argv=["nproc"], timeout=10),
            # DMI is readable without root on most systems; when it is not,
            # these fail harmlessly and the fields stay null.
            ssh.Command(argv=["cat", "/sys/class/dmi/id/product_name"], timeout=10),
            ssh.Command(argv=["cat", "/sys/class/dmi/id/product_serial"], timeout=10),
        ]
        batch = await ssh.run_many(creds, cmds)
        os_rel, kernel, host, uptime, loadavg, meminfo, nproc, product, serial = batch.results

        fields = _parse_os_release(os_rel.stdout) if os_rel.ok else {}
        os_family = _os_family_from_release(fields)
        pretty = fields.get("PRETTY_NAME") or fields.get("NAME") or None

        identity = _first_line(host) or creds.host

        uptime_seconds: int | None = None
        if uptime.ok and uptime.stdout.strip():
            try:
                uptime_seconds = int(float(uptime.stdout.split()[0]))
            except (ValueError, IndexError):
                uptime_seconds = None

        # Load average is not a percentage. Normalising by core count and
        # capping at 100 gives the same "how busy is this box" reading the
        # RouterOS driver reports, which is what the shared UI expects.
        cpu_load_pct: float | None = None
        if loadavg.ok and loadavg.stdout.strip():
            try:
                one_min = float(loadavg.stdout.split()[0])
                cores = int((nproc.stdout or "1").strip() or 1) if nproc.ok else 1
                cpu_load_pct = round(min(100.0, one_min / max(cores, 1) * 100.0), 1)
            except (ValueError, IndexError):
                cpu_load_pct = None

        memory_used_pct = _memory_used_pct(meminfo.stdout) if meminfo.ok else None

        return SystemInfo(
            identity=identity,
            model=_first_line(product),
            serial=_first_line(serial),
            firmware=_first_line(kernel),
            uptime_seconds=uptime_seconds,
            cpu_load_pct=cpu_load_pct,
            memory_used_pct=memory_used_pct,
            os_family=os_family,
            os_version=pretty,
            raw={
                "os_release": fields,
                "host_key_fingerprint": batch.host_key_fingerprint,
            },
        )

    async def system_reboot(self, creds: DeviceCredentials) -> None:
        # systemd closes the SSH session before replying, so a dropped
        # connection here is the expected outcome, not a failure.
        try:
            await ssh.run(creds, ["systemctl", "reboot"], become=True, timeout=15)
        except ssh.SshError as e:
            log.info("linux.reboot.session_dropped", host=creds.host, detail=str(e))

    # -------------------------------------------------------- networking

    async def interfaces_list(self, creds: DeviceCredentials) -> list[Interface]:
        batch = await ssh.run_many(
            creds, [ssh.Command(argv=["ip", "-j", "-s", "link", "show"], timeout=20)]
        )
        rows = _json_or_empty(batch.results[0], "listing interfaces")

        out: list[Interface] = []
        for r in rows:
            stats = (r.get("stats64") or {}) if isinstance(r.get("stats64"), dict) else {}
            rx = stats.get("rx") or {}
            tx = stats.get("tx") or {}
            flags = r.get("flags") or []
            out.append(
                Interface(
                    id=str(r.get("ifindex")) if r.get("ifindex") is not None else None,
                    name=r.get("ifname") or "",
                    type=r.get("link_type") or "unknown",
                    running=r.get("operstate") == "UP",
                    # "disabled" on RouterOS means administratively down,
                    # which is the absence of IFF_UP here.
                    disabled="UP" not in flags,
                    mac_address=r.get("address"),
                    mtu=r.get("mtu"),
                    actual_mtu=r.get("mtu"),
                    rx_bytes=rx.get("bytes"),
                    tx_bytes=tx.get("bytes"),
                    raw=r,
                )
            )
        return out

    async def ip_addresses_list(self, creds: DeviceCredentials) -> list[IpAddress]:
        batch = await ssh.run_many(
            creds, [ssh.Command(argv=["ip", "-j", "addr", "show"], timeout=20)]
        )
        rows = _json_or_empty(batch.results[0], "listing addresses")

        out: list[IpAddress] = []
        for iface in rows:
            name = iface.get("ifname")
            for info in iface.get("addr_info") or []:
                local = info.get("local")
                if not local:
                    continue
                prefix = info.get("prefixlen")
                out.append(
                    IpAddress(
                        id=f"{name}:{local}",
                        address=f"{local}/{prefix}" if prefix is not None else local,
                        interface=name,
                        # ip(8) reports a scope, not an enable flag; an
                        # address that exists is live by definition.
                        disabled=False,
                        raw={"interface": iface.get("ifname"), **info},
                    )
                )
        return out

    async def ip_routes_list(self, creds: DeviceCredentials) -> list[IpRoute]:
        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=["ip", "-j", "route", "show"], timeout=20),
                ssh.Command(argv=["ip", "-j", "-6", "route", "show"], timeout=20),
            ],
        )
        rows = _json_or_empty(batch.results[0], "listing routes")
        # IPv6 is best-effort: a host with IPv6 disabled makes this fail,
        # and that must not take the whole routing table down with it.
        if batch.results[1].ok:
            rows += _json_or_empty(batch.results[1], "listing IPv6 routes")

        out: list[IpRoute] = []
        for r in rows:
            dst = r.get("dst") or "default"
            out.append(
                IpRoute(
                    id=f"{dst}:{r.get('dev') or ''}:{r.get('gateway') or ''}",
                    dst_address="0.0.0.0/0" if dst == "default" else dst,
                    gateway=r.get("gateway") or r.get("dev"),
                    distance=r.get("metric"),
                    routing_table=r.get("table") or "main",
                    pref_src=r.get("prefsrc"),
                    vrf_interface=r.get("dev"),
                    active=True,
                    # protocol=kernel/dhcp/ra means learned, anything else
                    # (static, boot) means somebody configured it.
                    dynamic=r.get("protocol") in {"kernel", "dhcp", "ra", "redirect"},
                    static=r.get("protocol") in {"static", "boot", None},
                    raw=r,
                )
            )
        return out

    async def ip_arp_list(self, creds: DeviceCredentials) -> list[ArpEntry]:
        batch = await ssh.run_many(
            creds, [ssh.Command(argv=["ip", "-j", "neigh", "show"], timeout=20)]
        )
        rows = _json_or_empty(batch.results[0], "listing the ARP table")

        out: list[ArpEntry] = []
        for r in rows:
            state = r.get("state") or []
            out.append(
                ArpEntry(
                    id=f"{r.get('dst')}:{r.get('dev')}",
                    address=r.get("dst") or "",
                    mac_address=r.get("lladdr"),
                    interface=r.get("dev"),
                    # FAILED / INCOMPLETE entries are cache misses, not peers.
                    complete=bool(r.get("lladdr"))
                    and not ({"FAILED", "INCOMPLETE"} & set(state)),
                    dynamic="PERMANENT" not in state,
                    raw=r,
                )
            )
        return out

    # ------------------------------------------------------------ tools

    async def tool_ping(
        self, creds: DeviceCredentials, target: str, count: int = 4
    ) -> list[dict[str, Any]]:
        result = await ssh.run(
            creds,
            ["ping", "-n", "-c", str(max(1, min(count, 20))), "-w", "20", target],
            timeout=30,
        )
        return [{"output": result.stdout, "error": result.stderr, "rc": result.rc}]

    async def tool_traceroute(
        self, creds: DeviceCredentials, target: str
    ) -> list[dict[str, Any]]:
        result = await ssh.run(
            creds, ["traceroute", "-n", "-w", "2", "-q", "1", target], timeout=60
        )
        if result.rc == 127:
            raise ssh.SshError("traceroute is not installed on this host")
        return [{"output": result.stdout, "error": result.stderr, "rc": result.rc}]


_MEM_LINE = re.compile(r"^(\w+):\s+(\d+)\s+kB", re.MULTILINE)


def _memory_used_pct(meminfo: str) -> float | None:
    """Used memory as a percentage, the way `free` computes it.

    MemAvailable rather than MemFree on purpose: page cache is reclaimable,
    and reporting it as "used" makes every healthy Linux box look like it
    is out of memory.
    """
    values = {m.group(1): int(m.group(2)) for m in _MEM_LINE.finditer(meminfo)}
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total:
        return None
    if available is None:
        free = values.get("MemFree", 0)
        buffers = values.get("Buffers", 0)
        cached = values.get("Cached", 0)
        available = free + buffers + cached
    return round((total - available) / total * 100.0, 1)
