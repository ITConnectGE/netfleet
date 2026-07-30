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
    NtpClient,
    ProcessInfo,
    ScheduledJob,
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
        Capability.PROC_LIST,
        Capability.CRON,
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
