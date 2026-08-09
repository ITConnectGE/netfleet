"""Parsers for `ufw` output.

Recorded from real Ubuntu hosts. Every failure mode here is a misread rather
than a crash — a rule shown against the wrong port, or a configured firewall
rendered as an empty one — which is exactly the kind of bug that survives to
production, so the samples are kept verbatim including their trailing spaces.
"""

from __future__ import annotations

import pytest

from app.drivers.linux import (
    _is_missing_command,
    _parse_ufw_added,
    _parse_ufw_app_list,
    _parse_ufw_status,
    _ufw_rule_from_spec,
)

from helpers import fail, ok

ACTIVE = """Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)
New profiles: skip

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW IN    Anywhere
[ 2] 80,443/tcp                 ALLOW IN    Anywhere                   # web
[ 3] 3000 on eth0               ALLOW IN    Anywhere
[ 4] Anywhere                   DENY IN     192.168.1.5
[ 5] 22/tcp (v6)                ALLOW IN    Anywhere (v6)
[ 6] 80,443/tcp (v6)            ALLOW IN    Anywhere (v6)              # web
"""


def test_header_fields():
    s = _parse_ufw_status(ACTIVE)
    assert s.active is True
    assert s.logging == "on (low)"
    assert s.default_incoming == "deny"
    assert s.default_outgoing == "allow"
    assert s.default_routed == "disabled"


def test_v4_and_v6_halves_fold_into_one_rule():
    """`ufw allow 22/tcp` installs two numbered entries. Showing both makes
    the ruleset look duplicated and invites deleting "the extra one", which
    silently drops IPv6 access."""
    s = _parse_ufw_status(ACTIVE)
    ssh_rule = next(r for r in s.rules if r.destination == "22/tcp")
    assert ssh_rule.ip_version == "both"
    assert ssh_rule.position == 1
    assert ssh_rule.position_v6 == 5
    # Six table rows, four logical rules.
    assert len(s.rules) == 4


def test_interface_survives_the_to_column():
    """"3000 on eth0" has a space in it, so column-offset slicing loses the
    interface and reports the rule as applying everywhere."""
    s = _parse_ufw_status(ACTIVE)
    rule = next(r for r in s.rules if r.interface == "eth0")
    assert rule.destination == "3000"
    assert rule.source == "Anywhere"


def test_comment_is_not_mistaken_for_an_address():
    s = _parse_ufw_status(ACTIVE)
    web = next(r for r in s.rules if r.destination == "80,443/tcp")
    assert web.comment == "web"
    assert web.source == "Anywhere"


def test_deny_rule_keeps_its_direction_and_source():
    s = _parse_ufw_status(ACTIVE)
    deny = next(r for r in s.rules if r.action == "deny")
    assert deny.direction == "in"
    assert deny.source == "192.168.1.5"
    assert deny.destination == "Anywhere"


def test_routed_rules_are_read_as_forward():
    s = _parse_ufw_status(
        "Status: active\n\n"
        "     To                         Action      From\n"
        "[ 1] 53                         ALLOW FWD   Anywhere on eth1          \n"
    )
    assert s.rules[0].direction == "fwd"
    assert s.rules[0].interface == "eth1"


def test_limit_action():
    s = _parse_ufw_status(
        "Status: active\n\n[ 1] 22/tcp                     LIMIT IN    Anywhere\n"
    )
    assert s.rules[0].action == "limit"


def test_ipv6_literal_without_a_v6_marker():
    """A literal v6 source carries no "(v6)" tag — the colon is the only tell."""
    s = _parse_ufw_status(
        "Status: active\n\n[ 1] Anywhere                   ALLOW IN    2001:db8::/32\n"
    )
    assert s.rules[0].ip_version == "v6"


def test_inactive_status_reports_no_rules():
    """`ufw status` on a disabled firewall prints the header and nothing else.
    The driver falls back to `ufw show added` precisely because of this — a
    configured-but-off firewall must never render as an empty one."""
    s = _parse_ufw_status("Status: inactive\n")
    assert s.active is False
    assert s.rules == []


# ---------------- `ufw show added` ----------------

# `ufw_status` reads /etc/default/ufw too, so the canned batches below carry a
# fifth result. It is the only source of the default policy while ufw is off.
DEFAULTS = 'DEFAULT_INPUT_POLICY="DROP"\nDEFAULT_OUTPUT_POLICY="ACCEPT"\n'

ADDED = """Added user rules (see 'ufw status' for running firewall):
ufw allow 22/tcp
ufw allow 80,443/tcp comment 'web'
ufw allow from 10.0.0.0/8
ufw allow in on eth0 to any port 3000 proto tcp
ufw route allow from 192.168.10.0/24 to 10.0.0.0/8
ufw deny from 192.168.1.5 comment 'blocked host'
"""


def test_added_keeps_only_command_lines():
    lines = _parse_ufw_added(ADDED)
    assert len(lines) == 6
    assert lines[0] == "ufw allow 22/tcp"
    assert not any(line.startswith("Added user rules") for line in lines)


def test_spec_simple_port():
    r = _ufw_rule_from_spec("ufw allow 22/tcp")
    assert (r.action, r.destination, r.source) == ("allow", "22/tcp", "Anywhere")
    assert r.spec == "ufw allow 22/tcp"


def test_spec_source_only_rule():
    r = _ufw_rule_from_spec("ufw allow from 10.0.0.0/8")
    assert r.source == "10.0.0.0/8"
    assert r.destination == "Anywhere"


def test_spec_interface_port_and_proto():
    r = _ufw_rule_from_spec("ufw allow in on eth0 to any port 3000 proto tcp")
    assert r.interface == "eth0"
    assert r.direction == "in"
    # "to any port 3000" — the port is the useful half, "any" is not.
    assert r.destination == "3000/tcp"


def test_spec_route_becomes_forward():
    r = _ufw_rule_from_spec("ufw route allow from 192.168.10.0/24 to 10.0.0.0/8")
    assert r.direction == "fwd"
    assert r.source == "192.168.10.0/24"
    assert r.destination == "10.0.0.0/8"


def test_spec_comment_with_spaces():
    r = _ufw_rule_from_spec("ufw deny from 192.168.1.5 comment 'blocked host'")
    assert r.comment == "blocked host"
    assert r.action == "deny"


def test_app_profiles():
    profiles = _parse_ufw_app_list(
        "Available applications:\n  Apache Full\n  OpenSSH\n  Nginx HTTP\n"
    )
    assert profiles == ["Apache Full", "OpenSSH", "Nginx HTTP"]


# ---------------- missing-binary detection ----------------


def test_missing_ufw_is_not_a_failure():
    """A host with no ufw and a host whose ufw errored need different words on
    screen. sudo reports a missing binary as rc 1, not the 127 a shell gives."""
    assert _is_missing_command(fail("sudo: ufw: command not found")) is True
    assert _is_missing_command(fail("ufw: not found", rc=127)) is True
    assert _is_missing_command(fail("ERROR: You need to be root")) is False
    assert _is_missing_command(ok("ufw 0.36.1")) is False


# ---------------- driver behaviour around the parsers ----------------


@pytest.mark.asyncio
async def test_disabled_firewall_still_lists_its_rules(driver, creds, fake_ssh):
    """The bug this exists to prevent: `ufw status` on a disabled firewall
    prints "Status: inactive" and no rules, so a configured-but-off host would
    render as one with no firewall rules at all — the most dangerous thing
    this screen could get wrong."""
    fake_ssh.results(
        ok("ufw 0.36.1\n"),
        ok("Status: inactive\n"),
        ok(ADDED),
        ok("Available applications:\n  OpenSSH\n"),
        ok(DEFAULTS),
    )
    state = await driver.ufw_status(creds)

    assert state.installed is True
    assert state.active is False
    assert state.rules_from_added is True
    assert len(state.rules) == 6
    assert state.rules[0].destination == "22/tcp"
    # No numbering exists on an inactive firewall — claiming one would be a lie
    # the write stages could act on.
    assert all(r.position is None for r in state.rules)


@pytest.mark.asyncio
async def test_ufw_reads_are_escalated(driver, creds, fake_ssh):
    """`ufw status` returns "ERROR: You need to be root" to an unprivileged
    user — with a zero exit status on some versions, so the failure would be
    read as an empty ruleset."""
    fake_ssh.results(
        ok("ufw 0.36.1\n"),
        ok(ACTIVE),
        ok(ADDED),
        ok("Available applications:\n"),
        ok(DEFAULTS),
    )
    await driver.ufw_status(creds)
    assert all(c.become for c in fake_ssh.sent())


@pytest.mark.asyncio
async def test_host_without_ufw_reports_not_installed(driver, creds, fake_ssh):
    fake_ssh.results(
        fail("sudo: ufw: command not found"), ok(""), ok(""), ok(""), ok("")
    )
    state = await driver.ufw_status(creds)
    assert state.installed is False
    assert state.active is False
    assert state.rules == []


@pytest.mark.asyncio
async def test_specs_are_not_attached_when_the_counts_disagree(
    driver, creds, fake_ssh
):
    """`spec` is what a later delete will act on. ufw orders both listings the
    same way, but a v6-only rule can make them disagree — and pinning the
    wrong spec to a rule would delete the wrong one."""
    fake_ssh.results(
        ok("ufw 0.36.1\n"),
        ok(ACTIVE),                       # 4 logical rules
        ok("ufw allow 22/tcp\n"),         # 1 spec
        ok(""),
        ok(DEFAULTS),
    )
    state = await driver.ufw_status(creds)
    assert all(r.spec is None for r in state.rules)
