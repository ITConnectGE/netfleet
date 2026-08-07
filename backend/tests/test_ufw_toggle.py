"""Switching rules off and back on.

ufw has no disabled state — a rule is in the ruleset or it is not — so
"disabled" means removed from the host and remembered in NetFleet. That makes
this the one feature where NetFleet holds firewall state the host does not,
and the risks are specific to that: putting a rule back somewhere different
from where it was, or reinstalling a deny above the allow that keeps NetFleet
reachable.
"""

from __future__ import annotations

import pytest

from app.drivers.base import ManagementPath, UfwRule
from app.drivers.linux import (
    _insert_argv_from_spec,
    _ufw_rule_from_spec,
    ufw_would_lock_out,
)
from app.drivers.linux import ufw_project_inserted as _inserted

from helpers import ok

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


# ---------------- rebuilding the command ----------------


def test_a_disabled_rule_can_be_rebuilt_from_its_spec():
    """The spec is the whole record. If it cannot be turned back into a
    command, the rule is not disabled — it is lost."""
    assert _insert_argv_from_spec("ufw allow 22/tcp", 3) == [
        "ufw", "insert", "3", "allow", "22/tcp",
    ]


def test_restoring_a_routed_rule_keeps_ufw_grammar():
    argv = _insert_argv_from_spec("ufw route allow from 10.0.0.0/8 to any", 1)
    assert argv[:4] == ["ufw", "route", "insert", "1"]


def test_restoring_without_a_position_appends():
    assert _insert_argv_from_spec("ufw allow 22/tcp", None) == [
        "ufw", "allow", "22/tcp",
    ]


@pytest.mark.parametrize("spec", ["", "allow 22", "ufw", "ufw nonsense 22"])
def test_restoring_refuses_anything_that_is_not_a_rule(spec):
    with pytest.raises(ValueError):
        _insert_argv_from_spec(spec, 1)


def test_a_disabled_rule_still_renders_as_a_rule():
    """The stored spec is re-parsed for display rather than stored twice, so
    the disabled table shows the same columns as the live one."""
    parsed = _ufw_rule_from_spec("ufw deny from 192.168.1.5 comment 'noisy'")
    assert parsed.action == "deny"
    assert parsed.source == "192.168.1.5"
    assert parsed.comment == "noisy"


# ---------------- the position is a hint ----------------


@pytest.mark.asyncio
async def test_restore_clamps_a_position_past_the_end(driver, creds, fake_ssh):
    """The ruleset moves on while a rule is switched off. `ufw insert` errors
    on a position past the end, so a rule disabled at 9 in a ruleset now two
    long has to land at 3, not fail."""
    fake_ssh.single(ok("ufw allow 80/tcp\nufw allow 443/tcp\n"), ok("Rule inserted"))
    command, landed = await driver.ufw_rule_restore(
        creds, spec="ufw allow 22/tcp", position=9
    )
    assert landed == 3
    assert "insert 3" in command


@pytest.mark.asyncio
async def test_restore_keeps_a_position_that_still_exists(driver, creds, fake_ssh):
    fake_ssh.single(ok("ufw allow 80/tcp\nufw allow 443/tcp\n"), ok("Rule inserted"))
    _, landed = await driver.ufw_rule_restore(
        creds, spec="ufw allow 22/tcp", position=1
    )
    assert landed == 1


@pytest.mark.asyncio
async def test_restore_appends_when_no_position_was_recorded(
    driver, creds, fake_ssh
):
    fake_ssh.single(ok("ufw allow 80/tcp\n"), ok("Rule inserted"))
    _, landed = await driver.ufw_rule_restore(
        creds, spec="ufw allow 22/tcp", position=None
    )
    assert landed == 2


# ---------------- re-enabling is not automatically safe ----------------


def test_reenabling_a_deny_above_the_ssh_allow_is_a_lockout():
    """A rule coming back is as dangerous as one being moved: ufw is
    first-match, so where it returns decides whether it matters."""
    after = _inserted([ALLOW_SSH], DENY_ALL, 1)
    assert [r.action for r in after] == ["deny", "allow"]
    assert ufw_would_lock_out(after, PATH, "deny") is True


def test_reenabling_the_same_deny_below_the_allow_is_fine():
    after = _inserted([ALLOW_SSH], DENY_ALL, 2)
    assert ufw_would_lock_out(after, PATH, "deny") is False


def test_reenabling_appends_when_no_position_was_recorded():
    after = _inserted([ALLOW_SSH], DENY_ALL, None)
    assert after[-1] is DENY_ALL


def test_insert_position_is_clamped_in_the_projection_too():
    """The simulation has to model the same clamping the driver does, or it
    judges a placement the host would never produce."""
    assert _inserted([ALLOW_SSH], DENY_ALL, 99)[-1] is DENY_ALL
    assert _inserted([ALLOW_SSH], DENY_ALL, 0)[0] is DENY_ALL
