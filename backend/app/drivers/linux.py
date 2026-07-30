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
    DeviceClock,
    DeviceCredentials,
    DiskUsage,
    Interface,
    IpAddress,
    IpRoute,
    NtpClient,
    SupportsCapabilityFallback,
    SystemInfo,
    UnsupportedOperation,
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


class LinuxDriver(SupportsCapabilityFallback):
    """Agentless Linux management over SSH."""

    vendor = "linux"
    # One driver for every distribution on purpose. `vendor` selects how to
    # *talk* to a device, and Ubuntu, Debian, Rocky and Alpine all speak
    # plain SSH — the protocol is identical. What differs is a short list of
    # commands (package manager, a few unit names, firewall front-end), and
    # those branch on `os_family`, which is detected from /etc/os-release on
    # connect rather than declared by the operator. Splitting this into
    # per-distro vendors would duplicate the transport, onboarding, host-key
    # and capability layers to express a handful of command differences, and
    # would break the moment somebody picked the wrong one.
    display_name = "Linux / Unix (SSH)"

    capabilities: set[Capability] = {
        Capability.SYSTEM_INFO,
        Capability.SYSTEM_REBOOT,
        Capability.SYSTEM_CLOCK,
        Capability.DISK_USAGE,
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
        cores: int | None = None
        if nproc.ok:
            try:
                cores = int(nproc.stdout.strip())
            except ValueError:
                cores = None

        cpu_load_pct: float | None = None
        loads: list[float] = []
        if loadavg.ok and loadavg.stdout.strip():
            try:
                loads = [float(x) for x in loadavg.stdout.split()[:3]]
                cpu_load_pct = round(min(100.0, loads[0] / max(cores or 1, 1) * 100.0), 1)
            except (ValueError, IndexError):
                loads = []
                cpu_load_pct = None

        mem = _parse_meminfo(meminfo.stdout) if meminfo.ok else {}

        return SystemInfo(
            identity=identity,
            model=_first_line(product),
            serial=_first_line(serial),
            firmware=_first_line(kernel),
            uptime_seconds=uptime_seconds,
            cpu_load_pct=cpu_load_pct,
            memory_used_pct=mem.get("used_pct"),
            os_family=os_family,
            os_version=pretty,
            cpu_count=cores,
            load_avg_1=loads[0] if len(loads) > 0 else None,
            load_avg_5=loads[1] if len(loads) > 1 else None,
            load_avg_15=loads[2] if len(loads) > 2 else None,
            memory_total_bytes=mem.get("total"),
            memory_used_bytes=mem.get("used"),
            swap_total_bytes=mem.get("swap_total"),
            swap_used_bytes=mem.get("swap_used"),
            raw={
                "os_release": fields,
                "host_key_fingerprint": batch.host_key_fingerprint,
            },
        )

    async def disk_usage_list(self, creds: DeviceCredentials) -> list[DiskUsage]:
        # -P forces POSIX single-line output, so a long device name cannot
        # wrap and shift every column. Bytes and inodes are two separate
        # df invocations because no single flag reports both.
        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=["df", "-P", "-T", "-B1"], timeout=20),
                ssh.Command(argv=["df", "-P", "-i"], timeout=20),
            ],
        )
        blocks, inodes = batch.results
        if not blocks.ok:
            raise ssh.SshError(
                f"reading disk usage failed: {(blocks.stderr or blocks.stdout).strip()[:200]}"
            )

        inode_by_mount = _parse_df_inodes(inodes.stdout) if inodes.ok else {}
        out: list[DiskUsage] = []
        for row in _parse_df_blocks(blocks.stdout):
            # Pseudo-filesystems are noise on this screen: tmpfs, devtmpfs,
            # squashfs (every snap is one), overlay, cgroup and friends
            # report sizes nobody can act on.
            if row["fs_type"] in _PSEUDO_FS:
                continue
            inode = inode_by_mount.get(row["mount_point"], {})
            total = row["total"]
            used = row["used"]
            out.append(
                DiskUsage(
                    filesystem=row["filesystem"],
                    mount_point=row["mount_point"],
                    fs_type=row["fs_type"],
                    total_bytes=total,
                    used_bytes=used,
                    available_bytes=row["available"],
                    used_pct=(round(used / total * 100.0, 1) if total else None),
                    inodes_total=inode.get("total"),
                    inodes_used=inode.get("used"),
                    inodes_used_pct=inode.get("used_pct"),
                    raw=row,
                )
            )
        out.sort(key=lambda d: d.mount_point)
        return out

    async def system_reboot(self, creds: DeviceCredentials) -> None:
        # systemd closes the SSH session before replying, so a dropped
        # connection here is the expected outcome, not a failure.
        try:
            await ssh.run(creds, ["systemctl", "reboot"], become=True, timeout=15)
        except ssh.SshError as e:
            log.info("linux.reboot.session_dropped", host=creds.host, detail=str(e))

    # ----------------------------------------------------- clock and NTP

    async def clock_get(self, creds: DeviceCredentials) -> DeviceClock:
        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=["timedatectl", "show"], timeout=15),
                ssh.Command(argv=["date", "+%H:%M:%S|%Y-%m-%d|%z|%Z"], timeout=15),
            ],
        )
        td, now = batch.results
        props = _parse_kv(td.stdout) if td.ok else {}

        time_s = date_s = offset = None
        if now.ok and now.stdout.strip():
            parts = now.stdout.strip().split("|")
            if len(parts) == 4:
                time_s, date_s, raw_offset, _abbrev = parts
                # date(1) prints +0400; everyone else writes +04:00.
                offset = (
                    f"{raw_offset[:3]}:{raw_offset[3:]}"
                    if len(raw_offset) == 5
                    else raw_offset
                )

        return DeviceClock(
            time=time_s,
            date=date_s,
            time_zone_name=props.get("Timezone"),
            # systemd has no "autodetect" concept; the field exists for
            # RouterOS and stays null rather than inventing a value.
            time_zone_autodetect=None,
            gmt_offset=offset,
            dst_active=None,
            raw=props,
        )

    async def clock_set(
        self,
        creds: DeviceCredentials,
        *,
        time_zone_name: str | None = None,
        time_zone_autodetect: bool | None = None,
        time: str | None = None,
        date: str | None = None,
    ) -> None:
        cmds: list[ssh.Command] = []
        if time_zone_name:
            _assert_safe_timezone(time_zone_name)
            cmds.append(
                ssh.Command(
                    argv=["timedatectl", "set-timezone", time_zone_name],
                    become=True,
                    timeout=20,
                )
            )
        # Setting the wall clock by hand only works with NTP off — systemd
        # rejects it outright otherwise, so say why rather than letting the
        # raw timedatectl error through.
        if time or date:
            ntp = await self.ntp_client_get(creds)
            if ntp.enabled:
                raise UnsupportedOperation(
                    "the clock is managed by NTP on this host — turn NTP off "
                    "before setting the time by hand"
                )
            stamp = f"{date or ''} {time or ''}".strip()
            _assert_safe_timestamp(stamp)
            cmds.append(
                ssh.Command(
                    argv=["timedatectl", "set-time", stamp], become=True, timeout=20
                )
            )
        if not cmds:
            return
        batch = await ssh.run_many(creds, cmds)
        for r in batch.results:
            r.check("setting the clock")

    async def ntp_client_get(self, creds: DeviceCredentials) -> NtpClient:
        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=["timedatectl", "show"], timeout=15),
                ssh.Command(argv=["timedatectl", "show-timesync"], timeout=15),
                # chrony is the default on RHEL-family; without this its
                # servers would come back empty on exactly those hosts.
                ssh.Command(argv=["chronyc", "-n", "sources"], timeout=15),
            ],
        )
        show, timesync, chrony = batch.results
        props = _parse_kv(show.stdout) if show.ok else {}
        sync = _parse_kv(timesync.stdout) if timesync.ok else {}

        servers = sync.get("SystemNTPServers") or sync.get("LinkNTPServers") or ""
        if not servers.strip() and chrony.ok:
            servers = " ".join(_parse_chrony_sources(chrony.stdout))

        return NtpClient(
            enabled=(props.get("NTP") == "yes"),
            mode="unicast",
            servers=",".join(servers.split()) or None,
            primary=None,
            secondary=None,
            raw={
                **props,
                **sync,
                "provider": _ntp_provider(sync, chrony),
                "synchronized": props.get("NTPSynchronized") == "yes",
            },
        )

    async def ntp_client_set(
        self,
        creds: DeviceCredentials,
        *,
        enabled: bool | None = None,
        servers: str | None = None,
        primary: str | None = None,
        secondary: str | None = None,
        mode: str | None = None,
    ) -> None:
        # RouterOS callers pass primary/secondary; fold them into one list so
        # the same UI works against both platforms.
        server_list = [s.strip() for s in (servers or "").replace(",", " ").split() if s.strip()]
        for legacy in (primary, secondary):
            if legacy and legacy.strip() and legacy.strip() not in server_list:
                server_list.append(legacy.strip())
        for s in server_list:
            _assert_safe_ntp_server(s)

        cmds: list[ssh.Command] = []

        if server_list:
            provider = await self._timesync_provider(creds)
            if provider != "timesyncd":
                raise UnsupportedOperation(
                    f"this host synchronises time with {provider}, and NetFleet can "
                    "only edit the server list for systemd-timesyncd. Change it in "
                    f"the {provider} configuration on the host."
                )
            # A drop-in rather than an edit of timesyncd.conf: it survives
            # package upgrades and can be removed in one piece, and we never
            # have to parse and rewrite someone else's config file.
            content = (
                "# Managed by NetFleet. Remove this file to hand the NTP server\n"
                "# list back to the host's own configuration.\n"
                "[Time]\n"
                f"NTP={' '.join(server_list)}\n"
            )
            cmds += [
                ssh.Command(
                    argv=["mkdir", "-p", "/etc/systemd/timesyncd.conf.d"],
                    become=True,
                    timeout=15,
                ),
                ssh.Command(
                    argv=["tee", "/etc/systemd/timesyncd.conf.d/90-netfleet.conf"],
                    become=True,
                    stdin=content,
                    timeout=15,
                ),
            ]

        if enabled is not None:
            cmds.append(
                ssh.Command(
                    argv=["timedatectl", "set-ntp", "true" if enabled else "false"],
                    become=True,
                    timeout=20,
                )
            )
        # Restart last, so it picks up both the new server list and the
        # enable flag in one go.
        if server_list and enabled is not False:
            cmds.append(
                ssh.Command(
                    argv=["systemctl", "restart", "systemd-timesyncd"],
                    become=True,
                    timeout=30,
                )
            )

        if not cmds:
            return
        batch = await ssh.run_many(creds, cmds)
        for r in batch.results:
            r.check("configuring NTP")

    async def _timesync_provider(self, creds: DeviceCredentials) -> str:
        result = await ssh.run(
            creds, ["systemctl", "is-active", "systemd-timesyncd"], timeout=15
        )
        if result.stdout.strip() == "active":
            return "timesyncd"
        for unit, name in (("chronyd", "chrony"), ("chrony", "chrony"), ("ntpd", "ntpd")):
            r = await ssh.run(creds, ["systemctl", "is-active", unit], timeout=15)
            if r.stdout.strip() == "active":
                return name
        return "timesyncd"

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

# Filesystems that exist only in memory or per-package. Listing them buries
# the two or three real disks the operator came to look at.
_PSEUDO_FS = frozenset(
    {
        "tmpfs", "devtmpfs", "squashfs", "overlay", "aufs", "ramfs",
        "proc", "sysfs", "cgroup", "cgroup2", "devpts", "efivarfs",
        "debugfs", "tracefs", "mqueue", "hugetlbfs", "fusectl",
        "configfs", "securityfs", "pstore", "binfmt_misc", "autofs",
        "nsfs", "fuse.gvfsd-fuse", "fuse.portal", "iso9660",
    }
)

# Timezone names, NTP servers and timestamps all reach the host as argv
# elements, so nothing here can reach a shell. These checks exist to reject
# nonsense early with a message that names the field, rather than letting a
# raw `timedatectl` error surface.
_SAFE_TZ = re.compile(r"^[A-Za-z0-9+_-]+(/[A-Za-z0-9+_-]+){0,2}$")
_SAFE_NTP_SERVER = re.compile(r"^[A-Za-z0-9._:-]{1,253}$")
_SAFE_TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}([ T][0-9]{2}:[0-9]{2}(:[0-9]{2})?)?$|^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$")


def _assert_safe_timezone(tz: str) -> None:
    if not _SAFE_TZ.match(tz):
        raise UnsupportedOperation(
            f"'{tz}' is not a valid timezone name (expected e.g. Asia/Tbilisi)"
        )


def _assert_safe_ntp_server(server: str) -> None:
    if not _SAFE_NTP_SERVER.match(server):
        raise UnsupportedOperation(f"'{server}' is not a valid NTP server address")


def _assert_safe_timestamp(stamp: str) -> None:
    if not _SAFE_TIMESTAMP.match(stamp):
        raise UnsupportedOperation(
            f"'{stamp}' is not a valid time (expected 'YYYY-MM-DD HH:MM:SS')"
        )


def _parse_kv(text: str) -> dict[str, str]:
    """Parse `Key=Value` output — what `timedatectl show` emits."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def _parse_meminfo(meminfo: str) -> dict[str, Any]:
    """Memory totals and usage the way `free` computes them.

    MemAvailable rather than MemFree on purpose: page cache is reclaimable,
    and reporting it as "used" makes every healthy Linux box look like it
    is out of memory.
    """
    kb = {m.group(1): int(m.group(2)) for m in _MEM_LINE.finditer(meminfo)}
    total = kb.get("MemTotal")
    if not total:
        return {}
    available = kb.get("MemAvailable")
    if available is None:
        available = kb.get("MemFree", 0) + kb.get("Buffers", 0) + kb.get("Cached", 0)

    swap_total = kb.get("SwapTotal", 0)
    swap_used = swap_total - kb.get("SwapFree", 0)
    return {
        "total": total * 1024,
        "used": (total - available) * 1024,
        "used_pct": round((total - available) / total * 100.0, 1),
        "swap_total": swap_total * 1024,
        "swap_used": swap_used * 1024,
    }


def _parse_df_blocks(text: str) -> list[dict[str, Any]]:
    """Parse `df -P -T -B1`. -P guarantees one record per line."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 7:
            continue
        try:
            total, used, available = int(parts[2]), int(parts[3]), int(parts[4])
        except ValueError:
            continue
        rows.append(
            {
                "filesystem": parts[0],
                "fs_type": parts[1],
                "total": total,
                "used": used,
                "available": available,
                # -P pins the mount point to the last field, so a path with
                # spaces still lands intact.
                "mount_point": " ".join(parts[6:]),
            }
        )
    return rows


def _parse_df_inodes(text: str) -> dict[str, dict[str, Any]]:
    """Parse `df -P -i`, keyed by mount point."""
    out: dict[str, dict[str, Any]] = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            total, used = int(parts[1]), int(parts[2])
        except ValueError:
            continue
        mount = " ".join(parts[5:])
        out[mount] = {
            "total": total,
            "used": used,
            "used_pct": round(used / total * 100.0, 1) if total else None,
        }
    return out


def _parse_chrony_sources(text: str) -> list[str]:
    """Pull server addresses out of `chronyc -n sources`.

    Rows look like `^* 192.0.2.1  2  6  377  33  +1234us[...]`; the address
    is the second field once the two-character state prefix is dropped.
    """
    servers: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0][0] not in "^=#":
            continue
        candidate = parts[1] if len(parts[0]) <= 2 else parts[0][2:]
        if candidate and candidate not in servers:
            servers.append(candidate)
    return servers


def _ntp_provider(sync: dict[str, str], chrony: ssh.CommandResult) -> str:
    if sync:
        return "systemd-timesyncd"
    if chrony.ok:
        return "chrony"
    return "unknown"
