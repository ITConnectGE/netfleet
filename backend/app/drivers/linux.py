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
    DeviceGroup,
    DeviceUser,
    DirEntryUsage,
    DiskUsage,
    Interface,
    InterfaceConfig,
    IpAddress,
    IpRoute,
    ManagementPath,
    NtpClient,
    PackageState,
    PackageUpdate,
    ProcessInfo,
    ScheduledJob,
    SupportsCapabilityFallback,
    SystemInfo,
    UfwRule,
    UfwRuleSpec,
    UfwStatus,
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
        Capability.PROC_LIST,
        Capability.CRON,
        Capability.PKG_MANAGER,
        Capability.FIREWALL_UFW,
        Capability.SYSTEM_USER,
        Capability.INTERFACE_LIST,
        Capability.IP_ADDRESS,
        Capability.IP_ADDRESS_CONFIG,
        Capability.IP_ROUTE,
        # The kernel's ARP/NDP cache — not CDP/LLDP discovery, which a
        # server does not speak.
        Capability.IP_ARP,
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

    async def ntp_sync_now(self, creds: DeviceCredentials) -> str:
        """Force an immediate time sync and report what happened.

        There is no one command for this: timesyncd only re-syncs when the
        unit restarts, chrony has `makestep` for a one-shot correction, and
        neither exists on the other kind of host.
        """
        provider = await self._timesync_provider(creds)
        if provider == "chrony":
            r = await ssh.run(creds, ["chronyc", "makestep"], become=True, timeout=30)
            r.check("forcing a chrony step")
            return "chrony: requested an immediate step"

        batch = await ssh.run_many(
            creds,
            [
                # Toggling NTP off/on makes timesyncd re-poll straight away;
                # a plain restart can otherwise sit on its existing backoff.
                ssh.Command(argv=["timedatectl", "set-ntp", "false"], become=True, timeout=20),
                ssh.Command(argv=["timedatectl", "set-ntp", "true"], become=True, timeout=20),
            ],
        )
        for r in batch.results:
            r.check("restarting time synchronisation")
        return "systemd-timesyncd: re-synchronisation requested"

    # --------------------------------------------------------- processes

    async def processes_top(
        self, creds: DeviceCredentials, *, limit: int = 40
    ) -> list[ProcessInfo]:
        """The `htop` view: what is running and what it is costing.

        `ps` rather than `top -b`, because top's batch output changes shape
        with terminal width and locale while ps with an explicit format is
        a stable contract. `%cpu` from ps is an average over the process
        lifetime rather than an instantaneous sample — noted in the UI, and
        the reason the list is sorted by it rather than presented as live.
        """
        n = max(1, min(limit, 200))
        result = await ssh.run(
            creds,
            [
                "ps", "-eo",
                "pid=,user:32=,pcpu=,pmem=,rss=,stat=,lstart=,time=,nlwp=,args=",
                "--sort=-pcpu",
            ],
            timeout=30,
        )
        if not result.ok:
            raise ssh.SshError(
                f"listing processes failed: {(result.stderr or result.stdout).strip()[:200]}"
            )

        out: list[ProcessInfo] = []
        for line in result.stdout.splitlines():
            # Field layout: pid user pcpu pmem rss stat + lstart (five
            # fields of its own) + time nlwp, then args — which keeps its
            # spaces, so the split stops at 13 and takes the rest whole.
            parts = line.split(maxsplit=13)
            if len(parts) < 14:
                continue
            try:
                pid = int(parts[0])
                rss_kb = int(parts[4])
            except ValueError:
                continue
            out.append(
                ProcessInfo(
                    pid=pid,
                    user=parts[1],
                    cpu_pct=_maybe_float(parts[2]),
                    mem_pct=_maybe_float(parts[3]),
                    rss_bytes=rss_kb * 1024,
                    state=parts[5],
                    started=" ".join(parts[6:11]),
                    cpu_time=parts[11],
                    threads=_maybe_int(parts[12]),
                    command=parts[13],
                )
            )
            if len(out) >= n:
                break
        return out

    # ---------------------------------------------------------- packages

    async def _package_manager(self, creds: DeviceCredentials) -> str:
        """Which package manager the host actually has.

        Detected rather than derived from os_family: a Fedora box has dnf,
        an old CentOS has yum, and asking the host is cheaper than being
        wrong.
        """
        result = await ssh.run(
            creds,
            [
                "sh", "-c",
                "for m in apt-get dnf yum zypper apk; do "
                'command -v $m >/dev/null 2>&1 && { echo $m; exit 0; }; done; echo unknown',
            ],
            timeout=15,
        )
        found = (result.stdout or "").strip().splitlines()
        return (found[0] if found else "unknown").replace("apt-get", "apt")

    async def packages_state(self, creds: DeviceCredentials) -> PackageState:
        manager = await self._package_manager(creds)
        if manager not in {"apt", "dnf", "yum"}:
            raise UnsupportedOperation(
                f"package management for '{manager}' is not implemented yet"
            )

        if manager == "apt":
            listing = ssh.Command(
                # `apt list` warns about its unstable CLI on stderr; the
                # format itself has been stable for a decade and there is no
                # machine-readable alternative that reports candidates.
                argv=["apt", "list", "--upgradable"],
                timeout=60,
            )
        else:
            # dnf exits 100 when updates exist, 0 when none. Neither is a
            # failure, so the caller must not treat rc as one.
            listing = ssh.Command(argv=[manager, "-q", "list", "updates"], timeout=120)

        batch = await ssh.run_many(
            creds,
            [
                listing,
                ssh.Command(argv=["test", "-f", "/var/run/reboot-required"], timeout=10),
                ssh.Command(
                    argv=["cat", "/var/run/reboot-required.pkgs"], timeout=10
                ),
                # RHEL equivalent; absent on Debian, which is fine.
                ssh.Command(argv=["needs-restarting", "-r"], become=True, timeout=30),
                ssh.Command(
                    argv=["stat", "-c", "%y", "/var/lib/apt/periodic/update-success-stamp"],
                    timeout=10,
                ),
            ],
        )
        listing_r, reboot_flag, reboot_pkgs, needs_restarting, stamp = batch.results

        if manager == "apt":
            updates = _parse_apt_upgradable(listing_r.stdout)
        else:
            updates = _parse_dnf_updates(listing_r.stdout)

        reboot = reboot_flag.rc == 0
        if needs_restarting.ok is False and needs_restarting.rc == 1:
            # `needs-restarting -r` exits 1 when a reboot is needed.
            reboot = True

        return PackageState(
            manager=manager,
            updates=updates,
            security_count=sum(1 for u in updates if u.is_security),
            reboot_required=reboot,
            reboot_required_by=[
                p.strip() for p in reboot_pkgs.stdout.splitlines() if p.strip()
            ]
            if reboot_pkgs.ok
            else [],
            last_refreshed_iso=(stamp.stdout.strip() or None) if stamp.ok else None,
        )

    async def packages_refresh(self, creds: DeviceCredentials) -> str:
        manager = await self._package_manager(creds)
        if manager == "apt":
            argv = ["apt-get", "update", "-q"]
        elif manager in {"dnf", "yum"}:
            argv = [manager, "-q", "makecache"]
        else:
            raise UnsupportedOperation(
                f"package management for '{manager}' is not implemented yet"
            )
        result = await ssh.run(creds, argv, become=True, timeout=300)
        # apt-get update returns non-zero when *any* repository fails, even
        # if the rest refreshed. Report the output either way rather than
        # throwing away a mostly-successful refresh.
        if not result.ok and not result.stdout.strip():
            raise ssh.SshError(
                f"refreshing package lists failed: {result.stderr.strip()[:300]}"
            )
        return (result.stdout + result.stderr).strip()

    async def packages_upgrade(
        self,
        creds: DeviceCredentials,
        *,
        names: list[str] | None = None,
        security_only: bool = False,
        timeout: float = 1800.0,
    ) -> str:
        manager = await self._package_manager(creds)
        for n in names or []:
            _assert_safe_package_name(n)

        if manager == "apt":
            argv = [
                # No shell here, so the environment is set with env(1).
                # DEBIAN_FRONTEND stops debconf opening a dialog nobody can
                # answer, which otherwise hangs until the timeout.
                "env",
                "DEBIAN_FRONTEND=noninteractive",
                "apt-get",
                "-y",
                # Keep the administrator's config files. Without these two,
                # a package that ships a changed conffile either prompts
                # (hang) or silently replaces a file someone edited.
                "-o", "Dpkg::Options::=--force-confdef",
                "-o", "Dpkg::Options::=--force-confold",
            ]
            if security_only:
                raise UnsupportedOperation(
                    "apt cannot filter to security updates on its own; install "
                    "unattended-upgrades on the host for that"
                )
            argv += ["install", "--only-upgrade", *names] if names else ["upgrade"]
        elif manager in {"dnf", "yum"}:
            argv = [manager, "-y"]
            if security_only:
                argv.append("--security")
            argv += ["upgrade", *(names or [])]
        else:
            raise UnsupportedOperation(
                f"package management for '{manager}' is not implemented yet"
            )

        result = await ssh.run(creds, argv, become=True, timeout=timeout)
        output = (result.stdout + result.stderr).strip()
        if not result.ok:
            raise ssh.SshError(
                f"upgrade failed (exit {result.rc}): {output[-800:] or 'no output'}"
            )
        return output

    # ------------------------------------------------------------- ufw

    async def ufw_status(self, creds: DeviceCredentials) -> UfwStatus:
        """Read the host's ufw configuration.

        Three reads in one batch, and all three matter:

        * `ufw status numbered verbose` — the running ruleset, with the
          positions every later write needs.
        * `ufw show added` — the rules *as configured*. This is the only one
          that answers when ufw is switched off, because `ufw status` then
          prints "Status: inactive" and nothing else. It is also the
          authoritative rule spec: ufw renumbers on every delete, so a
          position is not an identifier.
        * `ufw app list` — profile names, so the UI can show "OpenSSH" as a
          known profile rather than an opaque string.
        """
        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=["ufw", "version"], become=True, timeout=15),
                ssh.Command(
                    argv=["ufw", "status", "numbered", "verbose"],
                    become=True,
                    timeout=30,
                ),
                ssh.Command(argv=["ufw", "show", "added"], become=True, timeout=30),
                ssh.Command(argv=["ufw", "app", "list"], become=True, timeout=20),
                # `ufw status verbose` prints the Default line only while ufw
                # is running. On a disabled firewall this file is the only way
                # to know what policy would apply if it were switched on —
                # which is exactly what the enable pre-flight has to reason
                # about.
                ssh.Command(argv=["cat", "/etc/default/ufw"], become=True, timeout=15),
            ],
        )
        version, status_r, added_r, apps_r, defaults_r = batch.results

        if _is_missing_command(version):
            # Not an error: plenty of hosts legitimately have no ufw, and the
            # UI needs to say so rather than show an empty ruleset.
            return UfwStatus(installed=False, active=False)

        if not status_r.ok:
            raise ssh.SshError(
                "reading the ufw status failed: "
                f"{(status_r.stderr or status_r.stdout).strip()[:200]}"
            )

        status = _parse_ufw_status(status_r.stdout)
        added = _parse_ufw_added(added_r.stdout) if added_r.ok else []

        if status.active:
            # Attach the spec from `ufw show added` so a later delete has a
            # stable handle. Only when the counts line up exactly: the two
            # commands order rules the same way, but a v6-only rule or ufw's
            # IPV6 setting can make them disagree, and pinning the wrong spec
            # to a rule would mean a later delete removes the wrong one.
            if len(added) == len(status.rules):
                for rule, spec in zip(status.rules, added, strict=True):
                    rule.spec = spec
        else:
            # Inactive: the numbered table was empty, so the configured rules
            # are all we have and they carry no positions.
            status.rules = [_ufw_rule_from_spec(s) for s in added]
            status.rules_from_added = True

        status.app_profiles = _parse_ufw_app_list(apps_r.stdout) if apps_r.ok else []
        if defaults_r.ok:
            _apply_ufw_default_policies(status, defaults_r.stdout)
        return status

    async def ufw_rule_add(
        self,
        creds: DeviceCredentials,
        spec: UfwRuleSpec,
        *,
        position: int | None = None,
    ) -> str:
        """Install one rule. Returns the command that was run.

        `position` maps to `ufw insert N`, which is 1-based. Omitting it
        appends, which is ufw's own default.
        """
        argv = _build_ufw_rule_argv(spec, position=position)
        result = await ssh.run(creds, argv, become=True, timeout=60)
        result.check("adding the firewall rule")
        return " ".join(argv)

    async def _ufw_added_count(self, creds: DeviceCredentials) -> int:
        result = await ssh.run(
            creds, ["ufw", "show", "added"], become=True, timeout=30
        )
        result.check("reading the configured rules")
        return len(_parse_ufw_added(result.stdout))

    async def ufw_rule_replace(
        self,
        creds: DeviceCredentials,
        *,
        old_spec: str,
        new_spec: UfwRuleSpec,
        position: int | None = None,
    ) -> str:
        """Edit a rule: insert the replacement, confirm it landed, remove the
        original.

        In that order, always. The reverse leaves a window with neither rule
        present, and if the rule being edited is the one keeping NetFleet
        reachable, that window is a lockout. Inserting first can at worst leave
        two overlapping rules for a moment, which is harmless.
        """
        insert_argv = _build_ufw_rule_argv(new_spec, position=position)
        delete_argv = _delete_argv_from_spec(old_spec)

        before = await self._ufw_added_count(creds)
        add_r = await ssh.run(creds, insert_argv, become=True, timeout=60)
        add_r.check("adding the replacement rule")

        # ufw refuses duplicates with "Skipping adding existing rule" and exit
        # status 0, so the count is the only honest signal. Deleting the
        # original after a skipped insert would remove the rule the operator
        # meant to keep and leave nothing behind it.
        if await self._ufw_added_count(creds) <= before:
            raise ssh.SshError(
                "ufw already has a rule identical to the edited one, so "
                "nothing was changed and the original is still in place."
            )

        del_r = await ssh.run(creds, delete_argv, become=True, timeout=60)
        del_r.check("removing the original rule")
        return f"{' '.join(insert_argv)} ; {' '.join(delete_argv)}"

    async def ufw_rule_move(
        self, creds: DeviceCredentials, *, spec: str, position: int
    ) -> str:
        """Move a rule to a new position: delete, then re-insert.

        The opposite order from an edit, and for a reason worth stating. A move
        produces a rule byte-identical to one already installed, and ufw
        refuses to add a duplicate — so insert-then-delete cannot work here.
        The reversed order leaves a brief window with the rule absent; both
        commands share one connection, so that window is a single round trip,
        and the guard's snapshot covers it if anything goes wrong inside it.
        """
        if position < 1:
            raise ValueError("a rule position is 1-based")
        delete_argv = _delete_argv_from_spec(spec)
        insert_argv = _insert_argv_from_spec(spec, position)

        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=delete_argv, become=True, timeout=60),
                ssh.Command(argv=insert_argv, become=True, timeout=60),
            ],
        )
        batch.results[0].check("removing the rule from its old position")
        batch.results[1].check("re-inserting the rule at its new position")
        return f"{' '.join(delete_argv)} ; {' '.join(insert_argv)}"

    async def ufw_rule_restore(
        self, creds: DeviceCredentials, *, spec: str, position: int | None
    ) -> tuple[str, int]:
        """Reinstall a rule NetFleet removed. Returns the command and the
        position it actually landed at.

        The stored position is a hint. The ruleset can change while a rule is
        switched off, so it is clamped to what currently exists — `ufw insert`
        errors on a position past the end — and the caller is told where the
        rule really went rather than being left to assume.
        """
        count = await self._ufw_added_count(creds)
        landed = count + 1 if position is None else min(max(position, 1), count + 1)

        argv = _insert_argv_from_spec(spec, landed)
        result = await ssh.run(creds, argv, become=True, timeout=60)
        result.check("restoring the firewall rule")
        return " ".join(argv), landed

    async def ufw_rule_delete(self, creds: DeviceCredentials, *, spec: str) -> str:
        """Delete by rule specification, never by number.

        ufw renumbers on every delete, so a position captured when the page
        rendered can address a different rule by the time the click lands.
        Deleting by spec also removes the IPv4 and IPv6 halves together, which
        deleting one number does not.
        """
        argv = _delete_argv_from_spec(spec)
        result = await ssh.run(creds, argv, become=True, timeout=60)
        result.check("deleting the firewall rule")
        return " ".join(argv)

    async def ufw_enable(
        self,
        creds: DeviceCredentials,
        *,
        allow_first: UfwRuleSpec | None = None,
    ) -> str:
        """Switch the firewall on, optionally installing a rule first.

        Both commands go in one batch, rule first. That ordering is the whole
        point: enabling with the stock `deny (incoming)` policy and no rule
        permitting the management path takes the host away, and a rule added
        afterwards would arrive over a connection that no longer works.

        `--force` because plain `ufw enable` asks "Command may disrupt existing
        ssh connections. Proceed with operation (y|n)?" and would hang on a
        channel nobody can answer.
        """
        commands: list[ssh.Command] = []
        if allow_first is not None:
            commands.append(
                ssh.Command(
                    argv=_build_ufw_rule_argv(allow_first), become=True, timeout=60
                )
            )
        commands.append(
            ssh.Command(argv=["ufw", "--force", "enable"], become=True, timeout=60)
        )

        batch = await ssh.run_many(creds, commands)
        if allow_first is not None:
            batch.results[0].check("adding the management rule before enabling")
        batch.results[-1].check("enabling the firewall")
        return " ; ".join(" ".join(c.argv) for c in commands)

    async def ufw_disable(self, creds: DeviceCredentials) -> str:
        argv = ["ufw", "--force", "disable"]
        result = await ssh.run(creds, argv, become=True, timeout=60)
        result.check("disabling the firewall")
        return " ".join(argv)

    # -------------------------------------------------- the lockout guard

    async def management_path(self, creds: DeviceCredentials) -> ManagementPath:
        """The address and port this host actually sees NetFleet arriving on.

        Read from `$SSH_CONNECTION` in the live session rather than from the
        organisation's configured egress IPs. Internal hosts are reached over
        a management VLAN or a WireGuard tunnel and never see NetFleet's
        external address, so protecting the configured one would whitelist an
        address the host cannot receive from — causing exactly the lockout the
        check exists to prevent.
        """
        result = await ssh.run(
            creds, ["printenv", "SSH_CONNECTION"], timeout=15
        )
        return _parse_ssh_connection(result.stdout if result.ok else "")

    async def guard_supported(self, creds: DeviceCredentials) -> bool:
        result = await ssh.run(creds, ["systemd-run", "--version"], timeout=15)
        return not _is_missing_command(result)

    async def ufw_guard_arm(
        self,
        creds: DeviceCredentials,
        *,
        token: str,
        window_seconds: int,
    ) -> str:
        """Snapshot the ufw ruleset and schedule its restoration.

        Returns the snapshot directory. Everything here happens *before* the
        change it protects, on the same connection where possible: a batch
        that dies halfway must never leave the change applied with no timer
        behind it.
        """
        _assert_safe_token(token)
        directory = f"{_GUARD_DIR_PREFIX}{token}"
        unit = f"{_GUARD_UNIT_PREFIX}{token}"
        script = _guard_restore_script(directory)

        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=["mkdir", "-p", directory], become=True, timeout=15),
                # One command per file rather than one `cp` with three sources:
                # user6.rules is absent on a host with IPv6 disabled, and a
                # combined copy would fail for all three because of it.
                *[
                    ssh.Command(
                        argv=["cp", "-a", f"/etc/ufw/{name}", f"{directory}/{name}"],
                        become=True,
                        timeout=15,
                    )
                    for name in _UFW_SNAPSHOT_FILES
                ],
                ssh.Command(
                    argv=["tee", f"{directory}/restore.sh"],
                    stdin=script,
                    become=True,
                    timeout=15,
                ),
                ssh.Command(
                    argv=[
                        "systemd-run",
                        f"--on-active={int(window_seconds)}",
                        f"--unit={unit}",
                        "--description=NetFleet firewall lockout guard",
                        "/bin/sh",
                        f"{directory}/restore.sh",
                    ],
                    become=True,
                    timeout=30,
                ),
            ],
        )
        mkdir_r, *rest = batch.results
        mkdir_r.check("creating the guard snapshot directory")
        # The copies are best-effort by design; the restore script skips any
        # file that was not captured. `ufw.conf` is the one that must exist.
        write_r, arm_r = rest[-2], rest[-1]
        write_r.check("writing the guard restore script")
        arm_r.check("scheduling the guard restore timer")
        return directory

    async def ufw_guard_cancel(self, creds: DeviceCredentials, *, token: str) -> None:
        """Disarm the timer and clean up. Safe to call more than once."""
        _assert_safe_token(token)
        unit = f"{_GUARD_UNIT_PREFIX}{token}"
        directory = f"{_GUARD_DIR_PREFIX}{token}"
        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(
                    argv=["systemctl", "stop", f"{unit}.timer"],
                    become=True,
                    timeout=30,
                ),
                # A transient unit that already fired lingers as failed;
                # clearing it keeps `systemctl --failed` honest on the host.
                ssh.Command(
                    argv=["systemctl", "reset-failed", f"{unit}.service"],
                    become=True,
                    timeout=20,
                ),
                ssh.Command(
                    argv=["rm", "-rf", directory], become=True, timeout=20
                ),
            ],
        )
        # Only the stop is worth failing over: the host restoring a ruleset it
        # was already going to keep is not an error worth surfacing.
        batch.results[0].check("cancelling the guard timer")

    async def ufw_guard_restore(self, creds: DeviceCredentials, *, token: str) -> None:
        """Restore the snapshot now, rather than waiting for the timer."""
        _assert_safe_token(token)
        directory = f"{_GUARD_DIR_PREFIX}{token}"
        result = await ssh.run(
            creds, ["/bin/sh", f"{directory}/restore.sh"], become=True, timeout=60
        )
        result.check("restoring the firewall snapshot")
        await self.ufw_guard_cancel(creds, token=token)

    # ------------------------------------------------- users and groups

    async def device_users_list(self, creds: DeviceCredentials) -> list[DeviceUser]:
        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=["getent", "passwd"], timeout=20),
                ssh.Command(argv=["getent", "group"], timeout=20),
                # Password status: L = locked, P = usable, NP = no password.
                # `passwd -S` needs root and is the only way to tell a locked
                # account from an enabled one.
                ssh.Command(argv=["passwd", "-Sa"], become=True, timeout=20),
                ssh.Command(argv=["lastlog"], timeout=25),
            ],
        )
        passwd_r, group_r, status_r, lastlog_r = batch.results
        if not passwd_r.ok:
            raise ssh.SshError(
                f"listing accounts failed: {(passwd_r.stderr or '').strip()[:200]}"
            )

        groups = _parse_group_file(group_r.stdout) if group_r.ok else []
        primary_by_gid = {g.gid: g.name for g in groups if g.gid is not None}
        secondary: dict[str, list[str]] = {}
        for g in groups:
            for member in g.members:
                secondary.setdefault(member, []).append(g.name)

        locked = _parse_passwd_status(status_r.stdout) if status_r.ok else {}
        last_login = _parse_lastlog(lastlog_r.stdout) if lastlog_r.ok else {}

        out: list[DeviceUser] = []
        for entry in _parse_passwd_file(passwd_r.stdout):
            name = entry["name"]
            uid = entry["uid"]
            primary = primary_by_gid.get(entry["gid"])
            member_of = list(dict.fromkeys([primary, *secondary.get(name, [])]))
            out.append(
                DeviceUser(
                    id=name,
                    name=name,
                    group=primary,
                    groups=[g for g in member_of if g],
                    uid=uid,
                    gid=entry["gid"],
                    shell=entry["shell"],
                    home=entry["home"],
                    comment=entry["gecos"] or None,
                    disabled=locked.get(name, False),
                    last_logged_in=last_login.get(name),
                    # Below 1000 is the system range on every distro we
                    # target; `nobody` sits at the top of the 32-bit range.
                    is_system=uid is not None and (uid < 1000 or uid == 65534),
                    is_protected=_is_protected(name, creds.username),
                )
            )
        out.sort(key=lambda u: (u.is_system, u.name))
        return out

    async def device_groups_list(self, creds: DeviceCredentials) -> list[DeviceGroup]:
        result = await ssh.run(creds, ["getent", "group"], timeout=20)
        if not result.ok:
            raise ssh.SshError("listing groups failed")
        groups = _parse_group_file(result.stdout)
        groups.sort(key=lambda g: (g.is_system, g.name))
        return groups

    async def device_user_add(
        self,
        creds: DeviceCredentials,
        *,
        username: str,
        password: str | None = None,
        groups: list[str] | None = None,
        shell: str | None = None,
        comment: str | None = None,
        create_home: bool = True,
    ) -> None:
        _assert_safe_account_name(username)
        for g in groups or []:
            _assert_safe_account_name(g)
        if shell:
            _assert_safe_path(shell)

        argv = ["useradd"]
        argv += ["--create-home"] if create_home else ["--no-create-home"]
        argv += ["--shell", shell or "/bin/bash"]
        if comment:
            # GECOS is comma-delimited; a comma would silently become the
            # next field (room number, phone…).
            argv += ["--comment", comment.replace(",", " ")]
        if groups:
            argv += ["--groups", ",".join(groups)]
        argv.append(username)

        cmds = [ssh.Command(argv=argv, become=True, timeout=30)]
        if password:
            cmds.append(_chpasswd(username, password))
        else:
            # No password means key-only, and useradd already leaves the
            # account locked for password auth — make that explicit rather
            # than depending on the default.
            cmds.append(
                ssh.Command(argv=["usermod", "--lock", username], become=True, timeout=20)
            )

        batch = await ssh.run_many(creds, cmds)
        batch.results[0].check(f"creating account '{username}'")
        batch.results[1].check(f"setting the password for '{username}'")

    async def device_user_set_password(
        self, creds: DeviceCredentials, username: str, new_password: str
    ) -> None:
        _assert_safe_account_name(username)
        _assert_not_protected(username, creds.username, "change the password of")
        result = await ssh.run_many(creds, [_chpasswd(username, new_password)])
        result.results[0].check(f"setting the password for '{username}'")

    async def device_user_set_disabled(
        self, creds: DeviceCredentials, username: str, disabled: bool
    ) -> None:
        _assert_safe_account_name(username)
        _assert_not_protected(username, creds.username, "lock")
        result = await ssh.run(
            creds,
            ["usermod", "--lock" if disabled else "--unlock", username],
            become=True,
            timeout=20,
        )
        result.check(("locking" if disabled else "unlocking") + f" '{username}'")

    async def device_user_set_groups(
        self, creds: DeviceCredentials, username: str, groups: list[str]
    ) -> None:
        _assert_safe_account_name(username)
        for g in groups:
            _assert_safe_account_name(g)
        # Deliberately allowed on protected accounts: adding the management
        # user to a group is a normal thing to want, and unlike locking it
        # cannot take away access.
        result = await ssh.run(
            creds,
            ["usermod", "--groups", ",".join(groups), username],
            become=True,
            timeout=25,
        )
        result.check(f"setting groups for '{username}'")

    async def device_user_remove(
        self, creds: DeviceCredentials, username: str, *, remove_home: bool = False
    ) -> None:
        _assert_safe_account_name(username)
        _assert_not_protected(username, creds.username, "delete")
        argv = ["userdel"]
        if remove_home:
            argv.append("--remove")
        argv.append(username)
        result = await ssh.run(creds, argv, become=True, timeout=40)
        result.check(f"deleting '{username}'")

    async def device_group_add(self, creds: DeviceCredentials, name: str) -> None:
        _assert_safe_account_name(name)
        result = await ssh.run(creds, ["groupadd", name], become=True, timeout=20)
        result.check(f"creating group '{name}'")

    async def device_group_remove(self, creds: DeviceCredentials, name: str) -> None:
        _assert_safe_account_name(name)
        if name in _PROTECTED_GROUPS:
            raise UnsupportedOperation(
                f"'{name}' is a system group and cannot be deleted through NetFleet"
            )
        result = await ssh.run(creds, ["groupdel", name], become=True, timeout=20)
        result.check(f"deleting group '{name}'")

    # --------------------------------------------------------- scheduled

    async def scheduled_jobs(self, creds: DeviceCredentials) -> list[ScheduledJob]:
        """Everything scheduled on the host, cron and systemd timers alike.

        Reading the spool directory rather than shelling `crontab -l` per
        account: a box can have hundreds of users, and that would be one
        SSH command each.
        """
        batch = await ssh.run_many(
            creds,
            [
                # Debian and RHEL disagree on the spool path; ask for both.
                ssh.Command(
                    argv=[
                        "sh", "-c",
                        "for f in /var/spool/cron/crontabs/* /var/spool/cron/*; do "
                        '[ -f "$f" ] && printf "##FILE %s\\n" "$f" && cat "$f"; done',
                    ],
                    become=True,
                    timeout=25,
                ),
                ssh.Command(
                    argv=[
                        "sh", "-c",
                        'for f in /etc/crontab /etc/cron.d/*; do [ -f "$f" ] && '
                        'printf "##FILE %s\\n" "$f" && cat "$f"; done',
                    ],
                    become=True,
                    timeout=25,
                ),
                ssh.Command(
                    argv=[
                        "sh", "-c",
                        "for d in hourly daily weekly monthly; do "
                        'for f in /etc/cron.$d/*; do [ -f "$f" ] && '
                        'printf "%s\\t%s\\n" "$d" "$f"; done; done',
                    ],
                    become=True,
                    timeout=25,
                ),
                # `systemctl show` with a glob emits stable KEY=VALUE blocks.
                # `list-timers` is column-formatted and its layout shifts
                # with terminal width and locale.
                ssh.Command(
                    argv=[
                        "systemctl", "show", "*.timer", "--no-pager",
                        "--property=Id,Description,NextElapseUSecRealtime,"
                        "LastTriggerUSec,Unit,TimersCalendar,ActiveState,UnitFileState",
                    ],
                    timeout=25,
                ),
            ],
        )
        user_r, system_r, runparts_r, timers_r = batch.results

        jobs: list[ScheduledJob] = []
        if user_r.ok:
            jobs += _parse_crontabs(user_r.stdout, source="user-crontab", has_user_field=False)
        if system_r.ok:
            jobs += _parse_crontabs(system_r.stdout, source="cron.d", has_user_field=True)
        if runparts_r.ok:
            for line in runparts_r.stdout.splitlines():
                period, _, path = line.partition("\t")
                if path:
                    jobs.append(
                        ScheduledJob(
                            source="run-parts",
                            schedule=f"@{period.strip()}",
                            command=path.strip(),
                            user="root",
                            origin=f"/etc/cron.{period.strip()}",
                        )
                    )
        if timers_r.ok:
            jobs += _parse_timers(timers_r.stdout)

        jobs.sort(key=lambda j: (j.source, j.user or "", j.command))
        return jobs

    # ------------------------------------------------------- disk detail

    async def disk_tree(
        self, creds: DeviceCredentials, path: str, *, depth: int = 1
    ) -> list[DirEntryUsage]:
        """Recursive sizes of a directory's immediate children.

        `du -x` stays on one filesystem: without it, expanding `/` walks
        every mount including network shares, and a single click can hang
        for minutes on an NFS server that is not answering.
        """
        _assert_safe_path(path)
        result = await ssh.run(
            creds,
            ["du", "-x", "-b", "--max-depth", str(max(1, min(depth, 3))), "--", path],
            become=True,
            # Walking a large tree is slow, and this is user-initiated, so
            # a generous ceiling beats a spurious timeout.
            timeout=120,
        )
        if not result.ok and not result.stdout.strip():
            raise ssh.SshError(
                f"reading directory sizes failed: "
                f"{(result.stderr or result.stdout).strip()[:200]}"
            )

        base = path.rstrip("/") or "/"
        out: list[DirEntryUsage] = []
        for line in result.stdout.splitlines():
            size_s, _, entry = line.partition("\t")
            entry = entry.strip()
            if not entry or entry == base:
                continue
            try:
                size = int(size_s)
            except ValueError:
                continue
            out.append(
                DirEntryUsage(
                    path=entry,
                    name=entry[len(base):].lstrip("/") or entry,
                    size_bytes=size,
                )
            )
        # Biggest first: the reason anyone opens this screen is to find what
        # ate the disk.
        out.sort(key=lambda e: e.size_bytes, reverse=True)
        return out

    # -------------------------------------------------------- networking

    async def interface_configs(
        self, creds: DeviceCredentials
    ) -> list[InterfaceConfig]:
        batch = await ssh.run_many(
            creds,
            [
                ssh.Command(argv=["ip", "-j", "-d", "-s", "addr", "show"], timeout=20),
                ssh.Command(argv=["ip", "-j", "route", "show", "default"], timeout=20),
                ssh.Command(argv=["resolvectl", "status", "--no-pager"], timeout=20),
                ssh.Command(argv=["cat", "/etc/resolv.conf"], timeout=15),
                # Lease files name the DHCP server and expiry, which nothing
                # else on the host reports.
                ssh.Command(
                    argv=["sh", "-c", "cat /run/systemd/netif/leases/* 2>/dev/null"],
                    timeout=15,
                ),
                ssh.Command(argv=["networkctl", "list", "--no-pager", "--no-legend"], timeout=20),
                ssh.Command(argv=["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device"], timeout=20),
            ],
        )
        addr_r, route_r, resolvectl_r, resolvconf_r, leases_r, networkctl_r, nmcli_r = (
            batch.results
        )

        rows = _json_or_empty(addr_r, "listing interfaces")
        routes = _json_or_empty(route_r, "reading the default route") if route_r.ok else []
        gateways = _default_gateways(routes)
        dns_by_iface, dns_search = _parse_resolvectl(resolvectl_r.stdout if resolvectl_r.ok else "")
        global_dns = _parse_resolv_conf(resolvconf_r.stdout if resolvconf_r.ok else "")
        leases = _parse_networkd_leases(leases_r.stdout if leases_r.ok else "")
        managed = _managed_by(
            networkctl_r.stdout if networkctl_r.ok else "",
            nmcli_r.stdout if nmcli_r.ok else "",
        )

        out: list[InterfaceConfig] = []
        for r in rows:
            name = r.get("ifname") or ""
            if not name:
                continue
            flags = r.get("flags") or []
            stats = r.get("stats64") if isinstance(r.get("stats64"), dict) else {}
            linkinfo = r.get("linkinfo") or {}
            kind = linkinfo.get("info_kind")
            vlan_id = (linkinfo.get("info_data") or {}).get("id") if kind == "vlan" else None

            v4 = [
                a for a in (r.get("addr_info") or []) if a.get("family") == "inet"
            ]
            addresses = [
                f"{a['local']}/{a['prefixlen']}"
                for a in (r.get("addr_info") or [])
                if a.get("local") and a.get("prefixlen") is not None
            ]
            lease = leases.get(name) or {}
            out.append(
                InterfaceConfig(
                    name=name,
                    mac_address=r.get("address"),
                    state=r.get("operstate"),
                    admin_up="UP" in flags,
                    mtu=r.get("mtu"),
                    type=kind or r.get("link_type"),
                    vlan_id=vlan_id,
                    vlan_parent=r.get("link") if kind == "vlan" else None,
                    method=_addr_method(v4, lease),
                    addresses=addresses,
                    netmask=_prefix_to_netmask(v4[0]["prefixlen"]) if v4 else None,
                    gateway=gateways.get(name),
                    dns_servers=dns_by_iface.get(name) or global_dns,
                    dns_search=dns_search,
                    dhcp_server=lease.get("server"),
                    lease_expires_iso=lease.get("expires"),
                    rx_bytes=(stats.get("rx") or {}).get("bytes"),
                    tx_bytes=(stats.get("tx") or {}).get("bytes"),
                    managed_by=managed.get(name),
                    raw=r,
                )
            )
        # Loopback last — it is never what anyone came to look at.
        out.sort(key=lambda i: (i.name == "lo", i.name))
        return out

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


_SAFE_PATH = re.compile(r"^/[^\x00-\x1f]*$")


# Accounts NetFleet will not modify. `root` because a mistake there ends
# the host's administrability, and the account NetFleet connects as because
# locking it ends NetFleet's own access — the operator would have to fix it
# from a console.
_PROTECTED_USERS = frozenset({"root"})
_PROTECTED_GROUPS = frozenset(
    {"root", "sudo", "wheel", "adm", "shadow", "sudoers", "users", "nogroup"}
)
# POSIX-portable account name, the same rule `useradd` enforces.
_SAFE_ACCOUNT = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def _assert_safe_account_name(name: str) -> None:
    if not _SAFE_ACCOUNT.match(name):
        raise UnsupportedOperation(
            f"'{name}' is not a valid account name "
            "(lowercase letters, digits, hyphen and underscore; max 32)"
        )


def _is_protected(name: str, management_user: str | None) -> bool:
    return name in _PROTECTED_USERS or name == management_user


def _assert_not_protected(name: str, management_user: str | None, action: str) -> None:
    if name in _PROTECTED_USERS:
        raise UnsupportedOperation(
            f"NetFleet will not {action} '{name}' — do it from a console if you "
            "really mean to"
        )
    if management_user and name == management_user:
        raise UnsupportedOperation(
            f"'{name}' is the account NetFleet manages this host with; "
            f"to {action} it you would lose access to the host"
        )


def _chpasswd(username: str, password: str) -> ssh.Command:
    """Set a password without it ever appearing in a command line.

    `chpasswd` reads `user:password` from stdin, so the secret never lands
    in argv where every process on the box can read it out of /proc.
    """
    return ssh.Command(
        argv=["chpasswd"],
        become=True,
        stdin=f"{username}:{password}\n",
        timeout=25,
    )


_SAFE_PACKAGE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9+._-]{0,127}$")


def _assert_safe_package_name(name: str) -> None:
    if not _SAFE_PACKAGE.match(name):
        raise UnsupportedOperation(f"'{name}' is not a valid package name")


def _parse_apt_upgradable(text: str) -> list[PackageUpdate]:
    """Parse `apt list --upgradable`.

    Lines look like:
        nginx/noble-security 1.24.0-2ubuntu7.1 amd64 [upgradable from: 1.24.0-2]
    The first line is "Listing..." and repeated runs can emit warnings on
    stdout, so anything without the expected shape is skipped rather than
    guessed at.
    """
    out: list[PackageUpdate] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or "/" not in line or line.startswith(("Listing", "WARNING", "N:")):
            continue
        head, _, rest = line.partition("/")
        parts = rest.split()
        if len(parts) < 2:
            continue
        suite = parts[0]
        current = None
        if "[upgradable from:" in line:
            current = line.split("[upgradable from:", 1)[1].strip().rstrip("]").strip()
        out.append(
            PackageUpdate(
                name=head,
                current_version=current,
                candidate_version=parts[1],
                # Ubuntu and Debian both name the pocket "<suite>-security".
                is_security="-security" in suite,
                origin=suite,
                architecture=parts[2] if len(parts) > 2 else None,
            )
        )
    return out


def _parse_dnf_updates(text: str) -> list[PackageUpdate]:
    """Parse `dnf -q list updates`: name.arch  version  repo."""
    out: list[PackageUpdate] = []
    for raw in text.splitlines():
        parts = raw.split()
        if len(parts) != 3 or raw.startswith(" ") or "." not in parts[0]:
            continue
        if parts[0].lower() in {"last", "available", "updated"}:
            continue
        name, _, arch = parts[0].rpartition(".")
        repo = parts[2]
        out.append(
            PackageUpdate(
                name=name or parts[0],
                candidate_version=parts[1],
                # RHEL-family security content lives in repos whose id ends
                # in -security, or is flagged by `updateinfo` — which needs
                # a separate call, so this is the cheap approximation.
                is_security="security" in repo.lower(),
                origin=repo,
                architecture=arch or None,
            )
        )
    return out


# ------------------------------------------------------------------ ufw
#
# ufw's table is column-aligned but both the To and From columns can contain
# spaces ("3000 on eth0", "Anywhere on eth1"), so every parser below splits on
# the action keyword rather than by character offset.

_UFW_NUMBERED_RE = re.compile(r"^\[\s*(\d+)\]\s+(.*)$")
# No IGNORECASE: ufw prints these uppercase in the table, and matching
# case-insensitively would let a lowercase interface or hostname masquerade as
# the action column.
_UFW_ACTION_RE = re.compile(r"\s+(ALLOW|DENY|REJECT|LIMIT)(?:\s+(IN|OUT|FWD))?\s+")
_UFW_DEFAULT_RE = re.compile(r"(\w+)\s+\((incoming|outgoing|routed)\)")
_UFW_ON_RE = re.compile(r"^(.*?)\s+on\s+(\S+)$")
_UFW_V6_MARKER = "(v6)"

# The lockout guard. Both names carry the guard token, so both are validated
# before interpolation — `rm -rf` runs against the directory one.
_GUARD_DIR_PREFIX = "/var/tmp/netfleet-guard-"
_GUARD_UNIT_PREFIX = "netfleet-guard-"
_GUARD_TOKEN_RE = re.compile(r"^[a-f0-9]{16,64}$")
# ufw.conf carries ENABLED=yes/no, so restoring it restores whether the
# firewall was on. user6.rules is absent on hosts with IPv6 off.
_UFW_SNAPSHOT_FILES = ("user.rules", "user6.rules", "ufw.conf")


def _assert_safe_token(token: str) -> None:
    if not _GUARD_TOKEN_RE.match(token or ""):
        raise ValueError("guard token must be lowercase hex")


def _guard_restore_script(directory: str) -> str:
    """The dead-man script left on the host.

    Restores the three ufw files and then puts the firewall back into the
    on/off state the snapshot recorded — `ufw --force enable` regenerates the
    live ruleset from the restored files, so this covers a rule change and an
    enable/disable equally.

    Written as POSIX sh, not bash: a minimal host image may have no bash, and
    a restore script that cannot run is worse than no guard at all because it
    looks like one.
    """
    return f"""#!/bin/sh
# NetFleet lockout guard.
#
# Restores the ufw configuration this host had before NetFleet changed it.
# Fires only if NetFleet does not cancel the timer in time — which is the
# case where NetFleet can no longer reach this host to cancel it.
set -e
D={directory}
UFW=$(command -v ufw 2>/dev/null || echo /usr/sbin/ufw)
for f in {" ".join(_UFW_SNAPSHOT_FILES)}; do
  if [ -f "$D/$f" ]; then
    cp -a "$D/$f" /etc/ufw/"$f"
  fi
done
if grep -q '^ENABLED=yes' /etc/ufw/ufw.conf 2>/dev/null; then
  "$UFW" --force enable
else
  "$UFW" --force disable
fi
rm -rf "$D"
"""


# ufw's own vocabulary. Anything outside these sets is rejected before it can
# reach the CLI: the argv transport prevents shell injection, but not a
# malformed rule that ufw half-accepts and renders as something else.
_UFW_ACTIONS = frozenset({"allow", "deny", "reject", "limit"})
_UFW_DIRECTIONS = frozenset({"in", "out", "fwd"})
_UFW_PROTOCOLS = frozenset({"tcp", "udp"})
_UFW_PORT_RE = re.compile(r"^\d{1,5}(:\d{1,5})?(,\d{1,5}(:\d{1,5})?)*$")
_UFW_IFACE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")


def _assert_safe_ufw_address(value: str, what: str) -> None:
    """An address must be `any`, or parse as an IP or CIDR.

    Hostnames are refused deliberately. ufw would resolve one at rule-creation
    time and freeze the answer, so a rule that reads `allow from db.example`
    silently stops matching the moment that name points somewhere else.
    """
    import ipaddress

    if value == "any":
        return
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as e:
        raise ValueError(
            f"{what} must be an IP address or CIDR range (or 'any'), not {value!r}"
        ) from e


def _assert_safe_ufw_spec(spec: UfwRuleSpec) -> None:
    if spec.action not in _UFW_ACTIONS:
        raise ValueError(f"unknown firewall action {spec.action!r}")
    if spec.direction not in _UFW_DIRECTIONS:
        raise ValueError(f"unknown direction {spec.direction!r}")
    if spec.protocol is not None and spec.protocol not in _UFW_PROTOCOLS:
        raise ValueError(f"unsupported protocol {spec.protocol!r}")
    if spec.port is not None and not _UFW_PORT_RE.match(spec.port):
        raise ValueError(
            f"{spec.port!r} is not a port, port range (80:90) or list (80,443)"
        )
    if spec.interface is not None and not _UFW_IFACE_RE.match(spec.interface):
        raise ValueError(f"{spec.interface!r} is not a valid interface name")
    if spec.from_address:
        _assert_safe_ufw_address(spec.from_address, "the source address")
    if spec.to_address:
        _assert_safe_ufw_address(spec.to_address, "the destination address")
    if spec.comment is not None:
        if any(ch in spec.comment for ch in "\r\n\x00"):
            raise ValueError("a rule comment cannot contain line breaks")
        if len(spec.comment) > 255:
            raise ValueError("a rule comment cannot exceed 255 characters")
    # ufw rejects a protocol with no port of its own accord, but its error
    # ("Bad port") names the wrong thing and sends people hunting.
    if spec.protocol and not spec.port:
        raise ValueError("a protocol needs a port — ufw cannot match one alone")


def _build_ufw_rule_argv(
    spec: UfwRuleSpec, *, position: int | None = None
) -> list[str]:
    """Assemble `ufw …` in the extended grammar.

    The extended form (`from … to … port … proto …`) is used even when the
    short form would do, because the short form's meaning depends on argument
    order and the extended form's does not.
    """
    _assert_safe_ufw_spec(spec)

    argv = ["ufw"]
    # `route` precedes `insert`: ufw's grammar is `ufw route insert NUM RULE`,
    # matching `ufw route delete RULE`.
    if spec.direction == "fwd":
        argv.append("route")
    if position is not None:
        if position < 1:
            raise ValueError("a rule position is 1-based")
        argv += ["insert", str(position)]
    argv.append(spec.action)
    if spec.direction in {"in", "out"}:
        argv.append(spec.direction)
    if spec.interface:
        argv += ["on", spec.interface]
    argv += ["from", spec.from_address or "any"]
    argv += ["to", spec.to_address or "any"]
    if spec.port:
        argv += ["port", spec.port]
    if spec.protocol:
        argv += ["proto", spec.protocol]
    if spec.comment:
        argv += ["comment", spec.comment]
    return argv


def _insert_argv_from_spec(spec: str, position: int | None) -> list[str]:
    """Turn a `ufw show added` line back into the command that installs it.

    `route` precedes `insert` — `ufw route insert N RULE` — matching the
    delete form.
    """
    tokens = spec.split()
    if not tokens or tokens[0] != "ufw":
        raise ValueError("a rule specification must start with 'ufw'")
    rest = tokens[1:]
    if not rest:
        raise ValueError("a rule specification needs a rule")

    argv = ["ufw"]
    if rest[0] == "route":
        argv.append("route")
        rest = rest[1:]
    if position is not None:
        if position < 1:
            raise ValueError("a rule position is 1-based")
        argv += ["insert", str(position)]
    if not rest or rest[0] not in _UFW_ACTIONS:
        raise ValueError(f"{spec!r} does not name a rule ufw can install")
    return argv + rest


def _delete_argv_from_spec(spec: str) -> list[str]:
    """Turn a `ufw show added` line into the command that removes it.

    `ufw allow 22/tcp`            -> ufw --force delete allow 22/tcp
    `ufw route allow from a to b` -> ufw --force route delete allow from a to b

    `route` stays in front of `delete`: ufw's grammar is `ufw route delete
    RULE`, and `ufw delete route …` is a different, invalid thing.
    """
    tokens = spec.split()
    if not tokens or tokens[0] != "ufw":
        raise ValueError("a rule specification must start with 'ufw'")
    rest = tokens[1:]
    if not rest:
        raise ValueError("a rule specification needs a rule")

    prefix = ["ufw", "--force"]
    if rest[0] == "route":
        prefix.append("route")
        rest = rest[1:]
    if not rest or rest[0] not in _UFW_ACTIONS:
        raise ValueError(f"{spec!r} does not name a rule ufw can delete")
    # The comment is part of the stored spec but not part of the rule's
    # identity — ufw matches on the rule itself and rejects the trailing
    # `comment` clause on a delete.
    if "comment" in rest:
        rest = rest[: rest.index("comment")]
    return prefix + ["delete"] + rest


def _ufw_port_of(destination: str) -> str | None:
    """The port a ufw "To" column names, or None when it names everything.

    "22/tcp" -> "22"   "80,443/tcp" -> "80,443"   "Anywhere" -> None
    """
    value = (destination or "").strip()
    if not value or value.lower() in {"anywhere", "any"}:
        return None
    return value.split("/", 1)[0].strip() or None


def _ufw_port_matches(port_spec: str, port: int) -> bool:
    """ufw ports can be a list, a range, or both: "80,443", "1024:65535"."""
    for part in port_spec.split(","):
        part = part.strip()
        if ":" in part:
            low, _, high = part.partition(":")
            try:
                if int(low) <= port <= int(high):
                    return True
            except ValueError:
                continue
        elif part.isdigit() and int(part) == port:
            return True
    return False


def _ufw_source_matches(source: str, address: str) -> bool:
    import ipaddress

    value = (source or "").strip()
    if not value or value.lower() in {"anywhere", "any"}:
        return True
    try:
        return ipaddress.ip_address(address) in ipaddress.ip_network(
            value, strict=False
        )
    except ValueError:
        # A source we cannot parse (a hostname ufw resolved once, say) is not
        # claimed as coverage. Overstating protection is the dangerous
        # direction: it makes a rule look redundant when it is the only one
        # holding the door open.
        return False


def _ufw_rule_matches_path(rule: UfwRule, path: ManagementPath) -> bool:
    """Whether this rule's selectors match NetFleet's own connection.

    Says nothing about whether it permits or blocks it — see `ufw_path_verdict`.
    """
    if not path.known or rule.direction != "in":
        return False
    port_spec = _ufw_port_of(rule.destination)
    if port_spec is not None and not _ufw_port_matches(
        port_spec, path.server_port or 0
    ):
        return False
    return _ufw_source_matches(rule.source, path.client_address or "")


def ufw_rule_covers_path(rule: UfwRule, path: ManagementPath) -> bool:
    """Whether this rule permits NetFleet's own connection.

    `limit` counts alongside `allow`, because it permits the connection and
    merely rate-limits new ones — treating it as a deny would let the last
    real rule be deleted.
    """
    return rule.action in {"allow", "limit"} and _ufw_rule_matches_path(rule, path)


def ufw_spec_covers_path(spec: UfwRuleSpec, path: ManagementPath) -> bool:
    """The same question about a rule that does not exist yet.

    Needed before an edit: the replacement has to be checked, not the original,
    or editing the one rule holding the door open sails straight through.
    """
    if not path.known or spec.direction != "in":
        return False
    if spec.action not in {"allow", "limit"}:
        return False
    if spec.port is not None and not _ufw_port_matches(
        spec.port, path.server_port or 0
    ):
        return False
    source = spec.from_address or "any"
    return _ufw_source_matches(source, path.client_address or "")


def ufw_path_verdict(rules: list[UfwRule], path: ManagementPath) -> str:
    """What ufw would do with NetFleet's own connection, walking rules in order.

    ufw is first-match. A deny placed *above* the allow that keeps NetFleet
    reachable takes the host away without deleting anything at all, which is
    why reordering needs this and not just a count of covering rules.

    Returns "allow", "deny", or "default" when nothing matches.
    """
    for rule in rules:
        if not _ufw_rule_matches_path(rule, path):
            continue
        return "allow" if rule.action in {"allow", "limit"} else "deny"
    return "default"


# The projections. Each returns the ruleset a change would leave behind, in
# the order it would leave it in, so `ufw_would_lock_out` can judge the result
# rather than the intent. Pure functions, kept beside the verdict they feed.


def ufw_projected_rule(spec: UfwRuleSpec) -> UfwRule:
    """The shape a rule that does not exist yet would have.

    Only the fields the verdict reads are filled; this never leaves the
    simulation, so inventing a position or an ip_version would be noise.
    """
    destination = spec.port or "Anywhere"
    if spec.port and spec.protocol:
        destination = f"{spec.port}/{spec.protocol}"
    return UfwRule(
        action=spec.action,
        direction=spec.direction,
        destination=destination,
        source=spec.from_address or "Anywhere",
        interface=spec.interface,
        comment=spec.comment,
    )


def ufw_project_deleted(rules: list[UfwRule], spec: str) -> list[UfwRule]:
    return [r for r in rules if r.spec != spec]


def ufw_project_inserted(
    rules: list[UfwRule], rule: UfwRule, position: int | None
) -> list[UfwRule]:
    """Clamped the same way the driver clamps it — a projection that models a
    placement the host would never produce judges the wrong ruleset."""
    if position is None:
        return [*rules, rule]
    index = min(max(position - 1, 0), len(rules))
    return rules[:index] + [rule] + rules[index:]


def ufw_project_replaced(
    rules: list[UfwRule], old_spec: str, new: UfwRule, position: int | None
) -> list[UfwRule]:
    remaining = ufw_project_deleted(rules, old_spec)
    if position is None:
        # With no position given, ufw appends — but an edit keeps the original
        # slot when we can still see where it was.
        original = next((i for i, r in enumerate(rules) if r.spec == old_spec), None)
        if original is None:
            return [*remaining, new]
        return remaining[:original] + [new] + remaining[original:]
    return ufw_project_inserted(remaining, new, position)


def ufw_project_moved(
    rules: list[UfwRule], spec: str, position: int
) -> list[UfwRule]:
    target = next((r for r in rules if r.spec == spec), None)
    if target is None:
        return rules
    return ufw_project_inserted(ufw_project_deleted(rules, spec), target, position)


def ufw_would_lock_out(
    rules_after: list[UfwRule], path: ManagementPath, default_incoming: str | None
) -> bool:
    """Whether this ruleset, in this order, would cut NetFleet off.

    Falling through to a default of `deny` counts: an empty ruleset on a host
    with the stock incoming policy is just as unreachable as an explicit deny.
    """
    if not path.known:
        # Nothing observed, so nothing can be reasoned about. The host-side
        # guard remains the backstop.
        return False
    verdict = ufw_path_verdict(rules_after, path)
    if verdict == "allow":
        return False
    if verdict == "deny":
        return True
    return (default_incoming or "deny").lower() == "deny"


def _parse_ssh_connection(text: str) -> ManagementPath:
    """`SSH_CONNECTION` is "<client ip> <client port> <server ip> <server port>".

    The client address here is what the host sees *after* any NAT, which is
    the only address a firewall rule can usefully name.
    """
    parts = text.split()
    if len(parts) < 4:
        return ManagementPath()
    port: int | None = None
    try:
        port = int(parts[3])
    except ValueError:
        port = None
    return ManagementPath(
        client_address=parts[0] or None,
        server_address=parts[2] or None,
        server_port=port,
    )


def _is_missing_command(result: ssh.CommandResult) -> bool:
    """Distinguish "the tool is not installed" from "the tool failed".

    Worth separating: a host with no ufw and a host whose ufw errored need
    different words on screen. sudo reports a missing binary as rc 1 with
    'command not found' on stderr rather than the 127 a shell would give, so
    both are checked.
    """
    if result.ok:
        return False
    blob = f"{result.stderr} {result.stdout}".lower()
    return (
        result.rc == 127
        or "command not found" in blob
        or "no such file or directory" in blob
    )


def _split_ufw_on_interface(value: str) -> tuple[str, str | None]:
    """Peel a trailing `on <iface>` off a To or From column."""
    m = _UFW_ON_RE.match(value)
    if m is None:
        return value, None
    return m.group(1).strip(), m.group(2)


def _parse_ufw_rule_line(position: int, rest: str) -> UfwRule | None:
    """One `[ 1] 22/tcp  ALLOW IN  Anywhere  # ssh` row."""
    comment = None
    body = rest
    hash_at = body.find("#")
    if hash_at != -1:
        # Safe to cut on the first '#': no address, port spec or interface
        # name can contain one, so the remainder is always the comment.
        comment = body[hash_at + 1 :].strip() or None
        body = body[:hash_at]

    m = _UFW_ACTION_RE.search(body)
    if m is None:
        return None

    destination = body[: m.start()].strip()
    source = body[m.end() :].strip()
    action = m.group(1).lower()
    direction = (m.group(2) or "in").lower()

    is_v6 = _UFW_V6_MARKER in destination or _UFW_V6_MARKER in source
    destination = destination.replace(_UFW_V6_MARKER, "").strip()
    source = source.replace(_UFW_V6_MARKER, "").strip()

    destination, dest_iface = _split_ufw_on_interface(destination)
    source, src_iface = _split_ufw_on_interface(source)

    return UfwRule(
        action=action,
        direction=direction,
        destination=destination,
        source=source,
        # A literal IPv6 address carries no "(v6)" marker, so the colon is the
        # tell. Ports and interface names never contain one.
        ip_version="v6" if is_v6 or ":" in destination or ":" in source else "v4",
        position=position,
        interface=dest_iface or src_iface,
        comment=comment,
    )


def _pair_ufw_rules(rules: list[UfwRule]) -> list[UfwRule]:
    """Fold each rule's IPv4 and IPv6 halves into a single entry.

    `ufw allow 22/tcp` installs two numbered entries. Showing both makes every
    ruleset look duplicated and invites deleting "the extra one", which
    silently drops IPv6 access.
    """
    out: list[UfwRule] = []
    seen: dict[tuple, UfwRule] = {}
    for rule in rules:
        key = (
            rule.action,
            rule.direction,
            rule.destination,
            rule.source,
            rule.interface,
            rule.comment,
        )
        existing = seen.get(key)
        if existing is None:
            seen[key] = rule
            out.append(rule)
            if rule.ip_version == "v6":
                rule.position, rule.position_v6 = None, rule.position
            continue
        if rule.ip_version == "v6":
            existing.position_v6 = rule.position
        else:
            existing.position = rule.position
        existing.ip_version = "both"
    return out


def _parse_ufw_status(text: str) -> UfwStatus:
    status = UfwStatus()
    rules: list[UfwRule] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low.startswith("status:"):
            status.active = stripped.split(":", 1)[1].strip().lower() == "active"
            continue
        if low.startswith("logging:"):
            status.logging = stripped.split(":", 1)[1].strip() or None
            continue
        if low.startswith("default:"):
            for policy, direction in _UFW_DEFAULT_RE.findall(stripped):
                setattr(status, f"default_{direction}", policy.lower())
            continue
        m = _UFW_NUMBERED_RE.match(stripped)
        if m is not None:
            rule = _parse_ufw_rule_line(int(m.group(1)), m.group(2))
            if rule is not None:
                rules.append(rule)
    status.rules = _pair_ufw_rules(rules)
    return status


def _parse_ufw_added(text: str) -> list[str]:
    """The `ufw …` command lines from `ufw show added`.

    These are the authoritative rule specifications — ufw renumbers on every
    delete, so a position is not a stable identifier.
    """
    return [
        line.strip() for line in text.splitlines() if line.strip().startswith("ufw ")
    ]


def _ufw_rule_from_spec(spec: str) -> UfwRule:
    """Render one `ufw show added` line as a rule, for a firewall that is off.

    Deliberately shallow. With ufw inactive there is no numbered table to
    check the result against, so this fills the columns it can recognise and
    keeps the original line in `spec` for everything else. Guessing harder
    would produce a confident-looking rule that does not match what ufw would
    actually install.
    """
    tokens = spec.split()
    if tokens and tokens[0] == "ufw":
        tokens = tokens[1:]

    comment = None
    if "comment" in tokens:
        i = tokens.index("comment")
        comment = " ".join(tokens[i + 1 :]).strip().strip("'\"") or None
        tokens = tokens[:i]

    direction = "in"
    if tokens and tokens[0] == "route":
        direction = "fwd"
        tokens = tokens[1:]

    action = tokens[0].lower() if tokens else "allow"
    tokens = tokens[1:]
    if tokens and tokens[0] in {"in", "out"}:
        direction = tokens[0]
        tokens = tokens[1:]

    interface: str | None = None
    source: str | None = None
    destination: str | None = None
    proto: str | None = None

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if tok == "on" and nxt:
            interface, i = nxt, i + 2
        elif tok == "from" and nxt:
            source, i = nxt, i + 2
        elif tok == "to" and nxt:
            destination, i = nxt, i + 2
        elif tok == "port" and nxt:
            # "to any port 3000" — the port is the useful half; "any" is not.
            destination = nxt if destination in (None, "any") else f"{destination} port {nxt}"
            i += 2
        elif tok == "proto" and nxt:
            proto, i = nxt, i + 2
        else:
            # A bare token: a port spec, or the name of an app profile. Which
            # one is not decided here — the caller has `ufw app list` and can
            # match it without guessing.
            destination, i = tok, i + 1

    if proto and destination and "/" not in destination:
        destination = f"{destination}/{proto}"

    return UfwRule(
        action=action,
        direction=direction,
        destination=destination or "Anywhere",
        source=source or "Anywhere",
        ip_version="v6" if ":" in f"{source or ''}{destination or ''}" else "v4",
        interface=interface,
        comment=comment,
        spec=spec,
    )


_UFW_POLICY_WORDS = {"drop": "deny", "reject": "reject", "accept": "allow"}
_UFW_DEFAULT_KEYS = {
    "DEFAULT_INPUT_POLICY": "default_incoming",
    "DEFAULT_OUTPUT_POLICY": "default_outgoing",
    "DEFAULT_FORWARD_POLICY": "default_routed",
}


def _apply_ufw_default_policies(status: UfwStatus, text: str) -> None:
    """Fill in default policies from `/etc/default/ufw`.

    Only where `ufw status verbose` did not already supply them: that command
    reports what is *running*, this file reports what is *configured*, and the
    running answer is the truthful one whenever there is one. On a disabled
    firewall there is none, and this is all we have.

    The file speaks iptables target names (DROP/ACCEPT/REJECT); ufw's own
    output speaks deny/allow/reject. Translated here so one vocabulary reaches
    the rest of the system.
    """
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        field = _UFW_DEFAULT_KEYS.get(key.strip())
        if field is None or getattr(status, field) is not None:
            continue
        word = _UFW_POLICY_WORDS.get(value.strip().strip('"').strip("'").lower())
        if word is not None:
            setattr(status, field, word)


def _parse_ufw_app_list(text: str) -> list[str]:
    out: list[str] = []
    started = False
    for line in text.splitlines():
        if line.strip().lower().startswith("available applications"):
            started = True
            continue
        if started and line.strip():
            out.append(line.strip())
    return out


def _parse_passwd_file(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) < 7:
            continue
        out.append(
            {
                "name": parts[0],
                "uid": _maybe_int(parts[2]),
                "gid": _maybe_int(parts[3]),
                "gecos": parts[4].split(",")[0].strip(),
                "home": parts[5],
                "shell": parts[6],
            }
        )
    return out


def _parse_group_file(text: str) -> list[DeviceGroup]:
    out: list[DeviceGroup] = []
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) < 4:
            continue
        gid = _maybe_int(parts[2])
        out.append(
            DeviceGroup(
                name=parts[0],
                gid=gid,
                members=[m for m in parts[3].split(",") if m],
                is_system=gid is not None and (gid < 1000 or gid == 65534),
            )
        )
    return out


def _parse_passwd_status(text: str) -> dict[str, bool]:
    """`passwd -Sa` → {account: locked}.

    Second field is L (locked), P (usable password) or NP (no password).
    NP is not locked but has no password either — treated as not locked,
    because on a key-only account that is the normal, working state.
    """
    out: dict[str, bool] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out[parts[0]] = parts[1] == "L"
    return out


def _parse_lastlog(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        parts = line.split(None, 3)
        if len(parts) < 2:
            continue
        if "**Never logged in**" in line:
            continue
        out[parts[0]] = parts[-1].strip()
    return out


_CRON_SHORTCUTS = {
    "@reboot", "@yearly", "@annually", "@monthly",
    "@weekly", "@daily", "@midnight", "@hourly",
}


def _parse_crontabs(
    text: str, *, source: str, has_user_field: bool
) -> list[ScheduledJob]:
    """Parse concatenated crontab files delimited by `##FILE <path>`.

    `/etc/crontab` and `/etc/cron.d/*` carry a user column between the
    schedule and the command; a user's own crontab does not. Getting that
    wrong silently shifts the command by one field.
    """
    jobs: list[ScheduledJob] = []
    current_file: str | None = None
    implied_user: str | None = None
    pending_comment: str | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("##FILE "):
            current_file = line[7:].strip()
            # A user crontab is named after its owner.
            implied_user = current_file.rsplit("/", 1)[-1] if current_file else None
            pending_comment = None
            continue
        if not line:
            pending_comment = None
            continue
        if line.startswith("#"):
            # Keep the last comment: it is usually the only description a
            # cron entry has, and often the only clue to what it is for.
            pending_comment = line.lstrip("#").strip() or None
            continue
        # Environment assignments (PATH=…, MAILTO=…) are not jobs.
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", line):
            continue

        if line.startswith("@"):
            parts = line.split(None, 1)
            if parts[0] not in _CRON_SHORTCUTS or len(parts) < 2:
                continue
            schedule, rest = parts[0], parts[1]
        else:
            parts = line.split(None, 5)
            if len(parts) < 6:
                continue
            schedule, rest = " ".join(parts[:5]), parts[5]

        user = implied_user
        command = rest
        if has_user_field:
            bits = rest.split(None, 1)
            if len(bits) < 2:
                continue
            user, command = bits[0], bits[1]

        jobs.append(
            ScheduledJob(
                source="system-crontab"
                if current_file == "/etc/crontab"
                else source,
                schedule=schedule,
                command=command,
                user=user,
                origin=current_file,
                comment=pending_comment,
            )
        )
        pending_comment = None
    return jobs


def _usec_to_iso(value: str) -> str | None:
    """systemd reports timestamps as microseconds since the epoch, and uses
    0 or the max value to mean 'never'."""
    try:
        usec = int(value)
    except ValueError:
        return None
    if usec <= 0 or usec >= 2**63 - 1:
        return None
    from datetime import UTC, datetime

    return datetime.fromtimestamp(usec / 1_000_000, UTC).isoformat()


def _parse_timers(text: str) -> list[ScheduledJob]:
    """Parse `systemctl show '*.timer'` — KEY=VALUE blocks, blank separated."""
    jobs: list[ScheduledJob] = []
    for block in text.split("\n\n"):
        props = _parse_kv(block)
        unit = props.get("Id")
        if not unit or not unit.endswith(".timer"):
            continue
        # TimersCalendar looks like: { OnCalendar=daily ; next_elapse=… }
        calendar = props.get("TimersCalendar", "")
        m = re.search(r"OnCalendar=([^;}]+)", calendar)
        schedule = (m.group(1).strip() if m else "") or "(not a calendar timer)"
        jobs.append(
            ScheduledJob(
                source="timer",
                schedule=schedule,
                command=props.get("Unit") or props.get("Description") or unit,
                user="root",
                enabled=props.get("UnitFileState") != "disabled"
                and props.get("ActiveState") == "active",
                origin=unit,
                unit=unit,
                activates=props.get("Unit"),
                next_run_iso=_usec_to_iso(props.get("NextElapseUSecRealtime", "")),
                last_run_iso=_usec_to_iso(props.get("LastTriggerUSec", "")),
                comment=props.get("Description"),
            )
        )
    return jobs


def _maybe_float(v: str) -> float | None:
    try:
        return float(v)
    except ValueError:
        return None


def _maybe_int(v: str) -> int | None:
    try:
        return int(v)
    except ValueError:
        return None


def _assert_safe_path(path: str) -> None:
    """Reject anything that is not a plain absolute path.

    Paths travel as argv elements so a shell cannot see them, but `..`
    still lets a caller walk out of wherever the UI thinks it is, and a
    relative path would resolve against the SSH user's home rather than
    the tree on screen.
    """
    if not _SAFE_PATH.match(path) or ".." in path.split("/"):
        raise UnsupportedOperation(f"'{path}' is not a valid absolute path")


def _prefix_to_netmask(prefix: int) -> str:
    bits = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if 0 <= prefix <= 32 else 0
    return ".".join(str((bits >> s) & 0xFF) for s in (24, 16, 8, 0))


def _default_gateways(routes: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in routes:
        dev, gw = r.get("dev"), r.get("gateway")
        if dev and gw and dev not in out:
            out[dev] = gw
    return out


def _addr_method(v4: list[dict[str, Any]], lease: dict[str, str]) -> str:
    """Decide whether an address was leased or configured.

    `ip` does not say. The two tells are a lease file naming the interface,
    and the `dynamic` flag the kernel sets on an address with a finite
    lifetime — which is what DHCP produces and static configuration does
    not.
    """
    if lease:
        return "dhcp"
    if not v4:
        return "unmanaged"
    if any(a.get("dynamic") for a in v4):
        return "dhcp"
    return "static"


def _parse_resolvectl(text: str) -> tuple[dict[str, list[str]], list[str]]:
    """Per-link DNS servers and the search domains from `resolvectl status`."""
    by_iface: dict[str, list[str]] = {}
    search: list[str] = []
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Link ") and "(" in line and ")" in line:
            current = line[line.index("(") + 1 : line.rindex(")")]
            continue
        if line.startswith("Current DNS Server:"):
            continue
        if line.startswith("DNS Servers:"):
            servers = line.split(":", 1)[1].split()
            if current:
                by_iface.setdefault(current, []).extend(servers)
            continue
        if line.startswith("DNS Domain:"):
            search.extend(d for d in line.split(":", 1)[1].split() if d != "~.")
    return by_iface, list(dict.fromkeys(search))


def _parse_resolv_conf(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        parts = raw.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            out.append(parts[1])
    return out


def _parse_networkd_leases(text: str) -> dict[str, dict[str, str]]:
    """Pull the DHCP server and lease expiry out of networkd lease files.

    The files are `KEY=value` blocks; interface identity comes from the
    ADDRESS/INTERFACE keys depending on systemd version, so both are read.
    """
    out: dict[str, dict[str, str]] = {}
    current: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if current:
                iface = current.get("INTERFACE") or current.get("NETWORK")
                if iface:
                    out[iface] = {
                        "server": current.get("SERVER_ADDRESS"),
                        "expires": current.get("LEASE_EXPIRES") or current.get("T2"),
                    }
                current = {}
            continue
        key, sep, value = line.partition("=")
        if sep:
            current[key.strip()] = value.strip()
    if current:
        iface = current.get("INTERFACE") or current.get("NETWORK")
        if iface:
            out[iface] = {
                "server": current.get("SERVER_ADDRESS"),
                "expires": current.get("LEASE_EXPIRES") or current.get("T2"),
            }
    return out


def _managed_by(networkctl: str, nmcli: str) -> dict[str, str]:
    """Which subsystem owns each interface.

    Matters before any write: changing an address that NetworkManager owns
    via networkd (or the reverse) appears to work and is undone at the next
    renew or reboot.
    """
    out: dict[str, str] = {}
    for raw in networkctl.splitlines():
        parts = raw.split()
        # IDX LINK TYPE OPERATIONAL SETUP
        if len(parts) >= 5 and parts[0].isdigit() and parts[-1] not in {"unmanaged", "pending"}:
            out[parts[1]] = "systemd-networkd"
    for raw in nmcli.splitlines():
        parts = raw.split(":")
        if len(parts) >= 2 and parts[1] not in {"unmanaged", ""}:
            out[parts[0]] = "NetworkManager"
    return out


def _ntp_provider(sync: dict[str, str], chrony: ssh.CommandResult) -> str:
    if sync:
        return "systemd-timesyncd"
    if chrony.ok:
        return "chrony"
    return "unknown"
