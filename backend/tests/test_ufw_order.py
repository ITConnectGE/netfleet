"""Editing and reordering rules, and the first-match reasoning behind both.

Reordering is the one firewall operation where nothing is added or removed and
the host can still become unreachable: ufw is first-match, so a deny moved
above the allow that keeps NetFleet reachable takes the host away without
deleting anything. Counting "how many rules cover us" cannot see that, which
is why these tests are about order rather than membership.
"""

from __future__ import annotations

import pytest

from app.drivers.base import ManagementPath, UfwRule, UfwRuleSpec
from app.drivers.linux import (
    _build_ufw_rule_argv,
    ufw_path_verdict,
    ufw_spec_covers_path,
    ufw_would_lock_out,
)

from helpers import fail, ok

PATH = ManagementPath(
    client_address="10.20.0.4", server_address="10.20.0.9", server_port=22
)


def rule(**kw) -> UfwRule:
    base = {
        "action": "allow",
        "direction": "in",
        "destination": "22/tcp",
        "source": "Anywhere",
        "spec": None,
    }
    return UfwRule(**{**base, **kw})


ALLOW_SSH = rule(spec="ufw allow 22/tcp")
DENY_ALL = rule(action="deny", destination="Anywhere", spec="ufw deny from any")
ALLOW_WEB = rule(destination="80/tcp", spec="ufw allow 80/tcp")


# ---------------- first-match ----------------


def test_allow_above_deny_keeps_us_reachable():
    assert ufw_path_verdict([ALLOW_SSH, DENY_ALL], PATH) == "allow"


def test_deny_above_allow_locks_us_out():
    """Same two rules, opposite order, opposite outcome. This is the case a
    coverage count is blind to."""
    assert ufw_path_verdict([DENY_ALL, ALLOW_SSH], PATH) == "deny"


def test_rules_that_do_not_match_are_skipped():
    assert ufw_path_verdict([ALLOW_WEB, ALLOW_SSH], PATH) == "allow"


def test_no_matching_rule_falls_through_to_the_default():
    assert ufw_path_verdict([ALLOW_WEB], PATH) == "default"


def test_falling_through_to_a_deny_default_is_a_lockout():
    """An empty ruleset on a host with the stock incoming policy is exactly as
    unreachable as an explicit deny."""
    assert ufw_would_lock_out([], PATH, "deny") is True
    assert ufw_would_lock_out([], PATH, "allow") is False
    assert ufw_would_lock_out([], PATH, None) is True   # deny is ufw's default


def test_reordering_alone_can_lock_us_out():
    assert ufw_would_lock_out([ALLOW_SSH, DENY_ALL], PATH, "deny") is False
    assert ufw_would_lock_out([DENY_ALL, ALLOW_SSH], PATH, "deny") is True


def test_nothing_is_judged_when_the_path_is_unknown():
    """With no observed address, every ruleset would read as a lockout and
    every change would be refused."""
    assert ufw_would_lock_out([], ManagementPath(), "deny") is False


# ---------------- a rule that does not exist yet ----------------


def test_replacement_rule_is_checked_not_the_original():
    """An edit has to be judged on what it produces. Checking the original
    would let someone edit the one rule holding the door open into one that
    does not."""
    keeps = UfwRuleSpec(action="allow", direction="in", port="22", protocol="tcp")
    breaks = UfwRuleSpec(action="allow", direction="in", port="80", protocol="tcp")
    assert ufw_spec_covers_path(keeps, PATH) is True
    assert ufw_spec_covers_path(breaks, PATH) is False


def test_a_spec_with_no_port_covers_everything():
    assert ufw_spec_covers_path(UfwRuleSpec(action="allow"), PATH) is True


def test_a_spec_scoped_to_another_source_does_not_cover_us():
    spec = UfwRuleSpec(action="allow", port="22", from_address="192.168.9.0/24")
    assert ufw_spec_covers_path(spec, PATH) is False


def test_a_deny_spec_never_counts_as_coverage():
    assert ufw_spec_covers_path(UfwRuleSpec(action="deny", port="22"), PATH) is False


# ---------------- edit: insert before delete ----------------


@pytest.mark.asyncio
async def test_edit_inserts_the_replacement_before_removing_the_original(
    driver, creds, fake_ssh
):
    """The reverse order leaves a window with neither rule present. If the rule
    being edited is the one keeping NetFleet reachable, that window is a
    lockout."""
    fake_ssh.single(
        ok("ufw allow 22/tcp\n"),                       # count before: 1
        ok("Rule inserted"),                            # the insert
        ok("ufw allow 22/tcp\nufw allow 2222/tcp\n"),   # count after: 2
        ok("Rule deleted"),                             # the delete
    )
    await driver.ufw_rule_replace(
        creds,
        old_spec="ufw allow 22/tcp",
        new_spec=UfwRuleSpec(port="2222", protocol="tcp"),
    )
    verbs = [c.argv for c in fake_ssh.sent() if c.argv[1] not in ("show",)]
    assert "insert" in verbs[0] or verbs[0][1] == "allow"
    assert "delete" in verbs[1]


@pytest.mark.asyncio
async def test_edit_stops_if_ufw_skipped_the_insert(driver, creds, fake_ssh):
    """ufw refuses duplicates with exit status 0 and a "Skipping" message, so
    the rule count is the only honest signal. Deleting the original after a
    skipped insert would remove the rule and leave nothing in its place."""
    fake_ssh.single(
        ok("ufw allow 22/tcp\n"),          # before: 1
        ok("Skipping adding existing rule"),
        ok("ufw allow 22/tcp\n"),          # after: still 1
    )
    with pytest.raises(Exception, match="identical"):
        await driver.ufw_rule_replace(
            creds,
            old_spec="ufw allow 22/tcp",
            new_spec=UfwRuleSpec(port="22", protocol="tcp"),
        )
    # The delete must not have been attempted.
    assert not any("delete" in c.argv for c in fake_ssh.sent())


@pytest.mark.asyncio
async def test_edit_reports_a_failed_insert_rather_than_deleting(
    driver, creds, fake_ssh
):
    fake_ssh.single(ok("ufw allow 22/tcp\n"), fail("ERROR: Bad port"))
    with pytest.raises(Exception, match="replacement rule"):
        await driver.ufw_rule_replace(
            creds,
            old_spec="ufw allow 22/tcp",
            new_spec=UfwRuleSpec(port="2222", protocol="tcp"),
        )
    assert not any("delete" in c.argv for c in fake_ssh.sent())


# ---------------- move: delete before insert, and why ----------------


@pytest.mark.asyncio
async def test_move_deletes_before_inserting(driver, creds, fake_ssh):
    """The opposite order from an edit. A move produces a rule identical to one
    already installed and ufw refuses duplicates, so insert-first cannot work
    here. Both commands share one connection, so the window is one round trip
    and the guard's snapshot covers it."""
    await driver.ufw_rule_move(creds, spec="ufw allow 22/tcp", position=2)
    argvs = [c.argv for c in fake_ssh.sent()]
    assert "delete" in argvs[0]
    assert argvs[1][:3] == ["ufw", "insert", "2"]


@pytest.mark.asyncio
async def test_move_of_a_routed_rule_keeps_ufw_grammar(driver, creds, fake_ssh):
    """`ufw route insert N RULE`, matching `ufw route delete RULE`."""
    await driver.ufw_rule_move(
        creds, spec="ufw route allow from 10.0.0.0/8 to any", position=1
    )
    insert = fake_ssh.sent()[1].argv
    assert insert[:4] == ["ufw", "route", "insert", "1"]


@pytest.mark.asyncio
async def test_move_rejects_a_zero_position(driver, creds, fake_ssh):
    with pytest.raises(ValueError):
        await driver.ufw_rule_move(creds, spec="ufw allow 22/tcp", position=0)


def test_route_and_insert_keep_their_order_when_building_a_rule():
    argv = _build_ufw_rule_argv(
        UfwRuleSpec(direction="fwd", from_address="10.0.0.0/8"), position=2
    )
    assert argv[:4] == ["ufw", "route", "insert", "2"]
