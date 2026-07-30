"""Parsers for command output the driver reads.

Recorded from real Ubuntu hosts. Column layouts and field counts are the
contract here, and getting one wrong misreports rather than crashes —
which is the failure mode worth testing.
"""

from __future__ import annotations

from app.drivers.linux import (
    _addr_method,
    _parse_crontabs,
    _parse_df_blocks,
    _parse_df_inodes,
    _parse_meminfo,
    _parse_passwd_status,
    _parse_resolvectl,
    _parse_timers,
    _prefix_to_netmask,
)


def test_meminfo_uses_available_not_free():
    """Counting page cache as used makes every healthy Linux box look full."""
    mem = _parse_meminfo(
        "MemTotal: 1000 kB\nMemFree: 100 kB\nCached: 500 kB\nMemAvailable: 600 kB\n"
    )
    assert mem["used_pct"] == 40.0        # not 90, which MemFree would give


def test_netmask_conversion():
    assert _prefix_to_netmask(24) == "255.255.255.0"
    assert _prefix_to_netmask(30) == "255.255.255.252"


def test_df_keeps_mount_points_containing_spaces():
    rows = _parse_df_blocks(
        "Filesystem Type 1B-blocks Used Available Capacity Mounted on\n"
        "/dev/sdb1 xfs 100 40 60 40% /srv/my data\n"
    )
    assert rows[0]["mount_point"] == "/srv/my data"


def test_df_inode_percentages():
    ino = _parse_df_inodes(
        "Filesystem Inodes IUsed IFree IUse% Mounted on\n"
        "/dev/vda1 1000 250 750 25% /\n"
    )
    assert ino["/"]["used_pct"] == 25.0


def test_crontab_user_column_is_mode_dependent():
    """/etc/cron.d has a user column, a user's own crontab does not.
    Confusing them shifts the command by one field."""
    line = "0 3 * * * root /usr/bin/backup.sh\n"
    with_user = _parse_crontabs(
        f"##FILE /etc/cron.d/backup\n{line}", source="cron.d", has_user_field=True
    )
    assert with_user[0].user == "root"
    assert with_user[0].command == "/usr/bin/backup.sh"

    without = _parse_crontabs(
        f"##FILE /var/spool/cron/crontabs/bob\n{line}",
        source="user-crontab",
        has_user_field=False,
    )
    assert without[0].user == "bob"
    assert without[0].command == "root /usr/bin/backup.sh"


def test_crontab_skips_environment_assignments():
    jobs = _parse_crontabs(
        "##FILE /var/spool/cron/crontabs/bob\nPATH=/usr/bin\nMAILTO=a@b.c\n"
        "@daily /run.sh\n",
        source="user-crontab",
        has_user_field=False,
    )
    assert len(jobs) == 1 and jobs[0].schedule == "@daily"


def test_timer_never_is_not_1970():
    """systemd writes 0 or INT64_MAX for 'never'."""
    jobs = _parse_timers(
        "Id=x.timer\nNextElapseUSecRealtime=0\nLastTriggerUSec=0\n"
        "Unit=x.service\nTimersCalendar={ OnCalendar=weekly }\n"
        "ActiveState=inactive\nUnitFileState=disabled\n"
    )
    assert jobs[0].next_run_iso is None
    assert jobs[0].last_run_iso is None
    assert jobs[0].enabled is False


def test_resolvectl_only_attributes_dns_to_the_link_it_belongs_to():
    by_iface, _ = _parse_resolvectl(
        "Link 2 (eth0)\nDNS Servers: 1.1.1.1\nLink 3 (eth1)\n"
    )
    assert by_iface == {"eth0": ["1.1.1.1"]}


def test_dhcp_detected_from_either_lease_file_or_kernel_flag():
    assert _addr_method([{"dynamic": True}], {}) == "dhcp"
    assert _addr_method([{}], {"server": "10.0.0.1"}) == "dhcp"
    assert _addr_method([{}], {}) == "static"
    assert _addr_method([], {}) == "unmanaged"


def test_passwd_status_treats_no_password_as_unlocked():
    """NP is a key-only account working normally, not a locked one."""
    status = _parse_passwd_status("a L x\nb P x\nc NP x\n")
    assert status == {"a": True, "b": False, "c": False}
