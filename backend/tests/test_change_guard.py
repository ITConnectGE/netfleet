"""The lockout guard's host-side half.

What is tested here is ordering and content, because both failure modes are
silent: a timer armed *after* the change leaves a window where a dropped
connection means a locked-out host with no recovery, and a restore script
that cannot run looks exactly like a guard that can.

The orchestration around these (probe, confirm, rollback) lives in
services/change_guard.py and needs a database, so it is covered by the
service tests rather than here.
"""

from __future__ import annotations

import pytest

from app.drivers.linux import (
    _assert_safe_token,
    _guard_restore_script,
    _parse_ssh_connection,
)

from helpers import fail, ok

TOKEN = "0123456789abcdef0123456789abcdef"


@pytest.mark.asyncio
async def test_timer_is_armed_before_the_change_can_be_applied(
    driver, creds, fake_ssh
):
    """The arming batch must be self-contained and end with systemd-run. If a
    caller could apply the change first, a connection dropped in between would
    leave the host changed with nothing scheduled to undo it."""
    await driver.ufw_guard_arm(creds, token=TOKEN, window_seconds=120)

    argvs = [c.argv for c in fake_ssh.sent()]
    assert argvs[0][0] == "mkdir"
    assert argvs[-1][0] == "systemd-run"
    # Nothing in the arming batch touches ufw itself.
    assert not any("ufw" in a[0] for a in argvs)


@pytest.mark.asyncio
async def test_arm_snapshots_the_file_that_records_enabled_state(
    driver, creds, fake_ssh
):
    """ufw.conf carries ENABLED=yes/no. Without it in the snapshot, a rollback
    of `ufw enable` would restore the rules but leave the firewall on."""
    await driver.ufw_guard_arm(creds, token=TOKEN, window_seconds=120)
    copied = [c.argv[2] for c in fake_ssh.sent() if c.argv[0] == "cp"]
    assert copied == [
        "/etc/ufw/user.rules",
        "/etc/ufw/user6.rules",
        "/etc/ufw/ufw.conf",
    ]


@pytest.mark.asyncio
async def test_each_file_is_copied_separately(driver, creds, fake_ssh):
    """user6.rules is absent on a host with IPv6 disabled. One `cp` with three
    sources fails for all three because of it, silently producing a snapshot
    that restores nothing."""
    await driver.ufw_guard_arm(creds, token=TOKEN, window_seconds=120)
    copies = [c.argv for c in fake_ssh.sent() if c.argv[0] == "cp"]
    assert len(copies) == 3
    assert all(len(c) == 4 for c in copies)  # cp -a <src> <dst>


@pytest.mark.asyncio
async def test_arm_passes_the_window_to_systemd(driver, creds, fake_ssh):
    await driver.ufw_guard_arm(creds, token=TOKEN, window_seconds=90)
    argv = fake_ssh.sent()[-1].argv
    assert "--on-active=90" in argv
    assert f"--unit=netfleet-guard-{TOKEN}" in argv


@pytest.mark.asyncio
async def test_arm_escalates_every_command(driver, creds, fake_ssh):
    """/etc/ufw and systemd-run both need root; an unprivileged arm would
    report success having scheduled nothing."""
    await driver.ufw_guard_arm(creds, token=TOKEN, window_seconds=120)
    assert all(c.become for c in fake_ssh.sent())


@pytest.mark.asyncio
async def test_arm_fails_loudly_when_the_timer_cannot_be_scheduled(
    driver, creds, fake_ssh
):
    """A guard that silently failed to arm is worse than no guard, because the
    caller proceeds believing it is protected."""
    fake_ssh.results(
        ok(),  # mkdir
        ok(),  # cp user.rules
        ok(),  # cp user6.rules
        ok(),  # cp ufw.conf
        ok(),  # tee restore.sh
        fail("Failed to start transient service"),
    )
    with pytest.raises(Exception, match="guard restore timer"):
        await driver.ufw_guard_arm(creds, token=TOKEN, window_seconds=120)


@pytest.mark.asyncio
async def test_cancel_stops_the_timer_not_just_the_service(driver, creds, fake_ssh):
    """`systemd-run --on-active` creates both a .timer and a .service. Stopping
    only the service leaves the timer to fire later and revert a change the
    operator already confirmed."""
    await driver.ufw_guard_cancel(creds, token=TOKEN)
    stopped = [c.argv for c in fake_ssh.sent() if c.argv[:2] == ["systemctl", "stop"]]
    assert stopped == [["systemctl", "stop", f"netfleet-guard-{TOKEN}.timer"]]


@pytest.mark.asyncio
async def test_restore_runs_the_script_then_disarms(driver, creds, fake_ssh):
    await driver.ufw_guard_restore(creds, token=TOKEN)
    argvs = [c.argv for c in fake_ssh.sent()]
    assert argvs[0] == ["/bin/sh", f"/var/tmp/netfleet-guard-{TOKEN}/restore.sh"]
    assert ["systemctl", "stop", f"netfleet-guard-{TOKEN}.timer"] in argvs


# ---------------- the restore script itself ----------------


def test_restore_script_puts_the_firewall_back_on_or_off():
    """A rule change and an `ufw enable` both roll back through this one
    script, so it has to read the restored ENABLED flag rather than assume."""
    script = _guard_restore_script("/var/tmp/netfleet-guard-x")
    assert "ENABLED=yes" in script
    assert "--force enable" in script
    assert "--force disable" in script


def test_restore_script_is_posix_sh():
    """A minimal host image may have no bash. A restore script that cannot run
    is worse than no guard, because it looks like one."""
    script = _guard_restore_script("/var/tmp/netfleet-guard-x")
    assert script.startswith("#!/bin/sh")
    assert "[[" not in script          # bash-only test syntax
    assert "function " not in script


def test_restore_script_tolerates_a_missing_ipv6_ruleset():
    """`set -e` plus an unguarded copy would abort the whole restore on a host
    with IPv6 disabled — leaving the firewall exactly as the failed change
    left it."""
    script = _guard_restore_script("/var/tmp/netfleet-guard-x")
    assert 'if [ -f "$D/$f" ]; then' in script


def test_restore_script_does_not_depend_on_path():
    """systemd-run's environment is not a login shell; /usr/sbin may be absent
    from PATH and ufw lives there."""
    script = _guard_restore_script("/var/tmp/netfleet-guard-x")
    assert "command -v ufw" in script
    assert "/usr/sbin/ufw" in script


# ---------------- token safety ----------------


def test_token_must_be_hex():
    """The token is interpolated into a path that `rm -rf` later runs against
    and into a systemd unit name."""
    _assert_safe_token(TOKEN)
    for bad in ["", "../../etc", "abc", "x" * 32, f"{TOKEN};rm -rf /", TOKEN.upper()]:
        with pytest.raises(ValueError):
            _assert_safe_token(bad)


# ---------------- management path ----------------


def test_management_path_is_read_from_the_live_connection():
    """The client address here is what the host sees after NAT — the only
    address a firewall rule can usefully name. The configured egress IP is
    wrong for any host reached over a tunnel or a management VLAN."""
    path = _parse_ssh_connection("10.20.0.4 54321 10.20.0.9 2222\n")
    assert path.client_address == "10.20.0.4"
    assert path.server_address == "10.20.0.9"
    assert path.server_port == 2222
    assert path.known is True


def test_management_path_unknown_when_the_variable_is_absent():
    """Some non-interactive paths strip SSH_CONNECTION. Guessing an address
    there would produce a confident, wrong firewall rule."""
    assert _parse_ssh_connection("").known is False
    assert _parse_ssh_connection("10.0.0.1 22").known is False


def test_management_path_survives_a_nonsense_port():
    path = _parse_ssh_connection("10.0.0.1 5 10.0.0.2 notaport")
    assert path.client_address == "10.0.0.1"
    assert path.server_port is None
    assert path.known is False
