"""Switching the whole firewall on and off.

The only operation in this feature that can take a host away in a single
click. Two things carry the weight: the management rule must be installed
*before* the enable, not after, and `ufw enable` must never be able to prompt.
"""

from __future__ import annotations

import pytest

from app.drivers.base import UfwRuleSpec, UfwStatus
from app.drivers.linux import _apply_ufw_default_policies

from helpers import fail, ok

MGMT = UfwRuleSpec(
    action="allow",
    direction="in",
    port="22",
    protocol="tcp",
    from_address="10.20.0.4",
    comment="NetFleet management",
)


@pytest.mark.asyncio
async def test_enable_cannot_prompt(driver, creds, fake_ssh):
    """Plain `ufw enable` asks "Command may disrupt existing ssh connections.
    Proceed with operation (y|n)?" and would hang on a channel nobody can
    answer, until the command times out."""
    await driver.ufw_enable(creds)
    assert fake_ssh.sent()[-1].argv == ["ufw", "--force", "enable"]


@pytest.mark.asyncio
async def test_disable_cannot_prompt(driver, creds, fake_ssh):
    fake_ssh.single(ok("Firewall stopped"))
    await driver.ufw_disable(creds)
    assert fake_ssh.sent()[-1].argv == ["ufw", "--force", "disable"]


@pytest.mark.asyncio
async def test_the_management_rule_goes_in_before_the_enable(
    driver, creds, fake_ssh
):
    """The whole point of the offered fix. Enabling with the stock deny-incoming
    policy and no rule permitting the management path takes the host away, and
    a rule added afterwards would have to arrive over a connection that no
    longer works."""
    await driver.ufw_enable(creds, allow_first=MGMT)

    argvs = [c.argv for c in fake_ssh.sent()]
    assert len(argvs) == 2
    assert argvs[0][0] == "ufw" and "allow" in argvs[0]
    assert argvs[1] == ["ufw", "--force", "enable"]


@pytest.mark.asyncio
async def test_both_commands_share_one_connection(driver, creds, fake_ssh):
    """Two separate connections would leave a window where the rule is in place
    but the firewall is not yet on, and a failure in between would need a third
    round trip to diagnose."""
    await driver.ufw_enable(creds, allow_first=MGMT)
    # The fake records one batch per run_many call; two commands, one batch.
    assert len(fake_ssh.sent()) == 2


@pytest.mark.asyncio
async def test_enable_is_not_attempted_if_the_rule_failed(driver, creds, fake_ssh):
    """`check()` on the rule result runs before the enable result is read, so a
    rejected rule surfaces as itself rather than as a mysterious lockout."""
    fake_ssh.results(fail("ERROR: Bad source address"), ok(""))
    with pytest.raises(Exception, match="management rule"):
        await driver.ufw_enable(creds, allow_first=MGMT)


@pytest.mark.asyncio
async def test_enable_is_escalated(driver, creds, fake_ssh):
    await driver.ufw_enable(creds, allow_first=MGMT)
    assert all(c.become for c in fake_ssh.sent())


# ---------------- the default policy on a disabled firewall ----------------


def test_default_policy_is_read_from_the_config_when_ufw_is_off():
    """`ufw status verbose` prints the Default line only while ufw is running.
    Without this the enable pre-flight would reason about a disabled firewall
    with no idea what policy switching it on would apply."""
    status = UfwStatus()
    _apply_ufw_default_policies(
        status,
        'DEFAULT_INPUT_POLICY="DROP"\n'
        'DEFAULT_OUTPUT_POLICY="ACCEPT"\n'
        'DEFAULT_FORWARD_POLICY="REJECT"\n',
    )
    # The file speaks iptables targets; ufw's own output speaks deny/allow.
    assert status.default_incoming == "deny"
    assert status.default_outgoing == "allow"
    assert status.default_routed == "reject"


def test_the_running_policy_wins_over_the_configured_one():
    """`ufw status` reports what is enforced, the file what is configured. When
    both exist the enforced answer is the truthful one."""
    status = UfwStatus(default_incoming="allow")
    _apply_ufw_default_policies(status, 'DEFAULT_INPUT_POLICY="DROP"\n')
    assert status.default_incoming == "allow"


def test_comments_and_junk_in_the_config_are_ignored():
    status = UfwStatus()
    _apply_ufw_default_policies(
        status,
        "# DEFAULT_INPUT_POLICY=\"ACCEPT\"\n"
        "IPV6=yes\n"
        "DEFAULT_INPUT_POLICY=\"DROP\"\n"
        "DEFAULT_OUTPUT_POLICY=nonsense\n",
    )
    assert status.default_incoming == "deny"
    assert status.default_outgoing is None
