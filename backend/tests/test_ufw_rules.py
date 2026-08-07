"""Building and removing ufw rules.

Two things are load-bearing here. A rule built slightly wrong is not a syntax
error — ufw accepts it and enforces something other than what was asked for.
And a delete addressed by number rather than by specification removes whatever
happens to be at that number *now*, which after any other delete is a
different rule.
"""

from __future__ import annotations

import pytest

from app.drivers.base import ManagementPath, UfwRule, UfwRuleSpec
from app.drivers.linux import (
    _build_ufw_rule_argv,
    _delete_argv_from_spec,
    ufw_rule_covers_path,
)

from helpers import ok


def argv(**kw) -> list[str]:
    return _build_ufw_rule_argv(UfwRuleSpec(**kw))


# ---------------- building ----------------


def test_simple_port_rule():
    assert argv(port="22", protocol="tcp") == [
        "ufw", "allow", "in", "from", "any", "to", "any", "port", "22", "proto", "tcp",
    ]


def test_extended_form_is_always_used():
    """The short form's meaning depends on argument order; the extended form's
    does not. `from`/`to` default to `any` rather than being omitted."""
    assert "from" in argv(port="22") and "to" in argv(port="22")


def test_source_restricted_rule():
    out = argv(action="deny", from_address="192.168.1.5")
    assert out[:2] == ["ufw", "deny"]
    assert "from" in out and "192.168.1.5" in out


def test_routed_rule_uses_the_route_keyword_and_drops_direction():
    """`ufw route allow in …` is not valid — a forwarded rule has no in/out."""
    out = argv(direction="fwd", from_address="10.0.0.0/8")
    assert out[1] == "route"
    assert "in" not in out and "out" not in out


def test_insert_position_is_one_based():
    out = _build_ufw_rule_argv(UfwRuleSpec(port="22"), position=3)
    assert out[:3] == ["ufw", "insert", "3"]
    with pytest.raises(ValueError):
        _build_ufw_rule_argv(UfwRuleSpec(port="22"), position=0)


def test_comment_is_passed_as_one_argument():
    """Quoting happens in the transport. Splitting it here would turn the tail
    of the comment into rule tokens ufw then rejects or misreads."""
    out = argv(port="22", comment="ssh from the office")
    assert out[-2:] == ["comment", "ssh from the office"]


def test_port_list_and_range_are_accepted():
    assert "80,443" in argv(port="80,443", protocol="tcp")
    assert "1024:65535" in argv(port="1024:65535", protocol="tcp")


@pytest.mark.parametrize(
    "kw",
    [
        {"action": "drop"},                       # RouterOS' word, not ufw's
        {"direction": "sideways"},
        {"protocol": "icmp", "port": "1"},        # ufw has no proto icmp here
        {"port": "22; rm -rf /"},
        {"port": "http"},
        {"interface": "eth0; reboot"},
        {"from_address": "db.example.com"},       # resolved once, then stale
        {"from_address": "not-an-address"},
        {"port": "22", "comment": "line\nbreak"},
        {"protocol": "tcp"},                      # a protocol with no port
    ],
)
def test_malformed_rules_are_refused_before_reaching_ufw(kw):
    """The argv transport stops shell injection, but not a rule ufw
    half-accepts and then enforces as something else."""
    with pytest.raises(ValueError):
        argv(**kw)


# ---------------- deleting ----------------


def test_delete_is_built_from_the_specification():
    assert _delete_argv_from_spec("ufw allow 22/tcp") == [
        "ufw", "--force", "delete", "allow", "22/tcp",
    ]


def test_delete_keeps_route_in_front_of_delete():
    """ufw's grammar is `ufw route delete RULE`. `ufw delete route …` is a
    different and invalid thing."""
    out = _delete_argv_from_spec("ufw route allow from 10.0.0.0/8 to any")
    assert out[:4] == ["ufw", "--force", "route", "delete"]


def test_delete_drops_the_comment_clause():
    """The comment is part of the stored spec but not of the rule's identity;
    ufw rejects a trailing `comment` on a delete."""
    out = _delete_argv_from_spec("ufw allow 22/tcp comment 'ssh'")
    assert "comment" not in out
    assert out[-1] == "22/tcp"


def test_delete_forces_so_it_cannot_prompt():
    """An interactive prompt on a non-interactive channel hangs until the
    command times out."""
    assert "--force" in _delete_argv_from_spec("ufw allow 22/tcp")


@pytest.mark.parametrize(
    "spec", ["", "allow 22", "ufw", "ufw nonsense 22", "rm -rf /"]
)
def test_delete_refuses_anything_that_is_not_a_rule(spec):
    with pytest.raises(ValueError):
        _delete_argv_from_spec(spec)


@pytest.mark.asyncio
async def test_rule_writes_are_escalated(driver, creds, fake_ssh):
    fake_ssh.single(ok(), ok())
    await driver.ufw_rule_add(creds, UfwRuleSpec(port="22", protocol="tcp"))
    await driver.ufw_rule_delete(creds, spec="ufw allow 22/tcp")
    assert all(c.become for c in fake_ssh.sent())


# ---------------- management-path protection ----------------

PATH = ManagementPath(
    client_address="10.20.0.4", server_address="10.20.0.9", server_port=22
)


def rule(**kw) -> UfwRule:
    base = {
        "action": "allow",
        "direction": "in",
        "destination": "22/tcp",
        "source": "Anywhere",
    }
    return UfwRule(**{**base, **kw})


def test_open_ssh_rule_covers_the_management_path():
    assert ufw_rule_covers_path(rule(), PATH) is True


def test_rule_scoped_to_our_subnet_covers_us():
    assert ufw_rule_covers_path(rule(source="10.20.0.0/24"), PATH) is True


def test_rule_scoped_to_someone_elses_subnet_does_not():
    assert ufw_rule_covers_path(rule(source="192.168.5.0/24"), PATH) is False


def test_rule_on_another_port_does_not_cover_us():
    assert ufw_rule_covers_path(rule(destination="80/tcp"), PATH) is False


def test_anywhere_destination_covers_every_port():
    assert ufw_rule_covers_path(rule(destination="Anywhere"), PATH) is True


def test_port_range_covers_a_port_inside_it():
    assert ufw_rule_covers_path(rule(destination="20:30/tcp"), PATH) is True
    assert ufw_rule_covers_path(rule(destination="30:40/tcp"), PATH) is False


def test_port_list_covers_a_listed_port():
    assert ufw_rule_covers_path(rule(destination="22,80/tcp"), PATH) is True


def test_limit_counts_as_coverage():
    """`limit` permits the connection — it only rate-limits new ones. Treating
    it as a deny would let the last real rule be deleted."""
    assert ufw_rule_covers_path(rule(action="limit"), PATH) is True


def test_deny_and_outbound_rules_are_not_coverage():
    assert ufw_rule_covers_path(rule(action="deny"), PATH) is False
    assert ufw_rule_covers_path(rule(direction="out"), PATH) is False


def test_unparseable_source_is_not_claimed_as_coverage():
    """Overstating protection is the dangerous direction: it makes a rule look
    redundant when it is the only one holding the door open."""
    assert ufw_rule_covers_path(rule(source="some-host.internal"), PATH) is False


def test_nothing_is_protected_when_the_path_is_unknown():
    """With no observed address there is nothing to reason about, and inventing
    one would refuse deletes for a rule that protects nobody."""
    assert ufw_rule_covers_path(rule(), ManagementPath()) is False
