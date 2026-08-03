"""Package listing and upgrades.

The upgrade flags get the most attention: the difference between a clean
`apt-get upgrade` and one that hangs forever or silently overwrites an
edited config file is entirely in the arguments.
"""

from __future__ import annotations

import pytest

from app.drivers.base import UnsupportedOperation
from app.drivers.linux import _parse_apt_upgradable, _parse_dnf_updates
from helpers import fail, ok

APT_LIST = """Listing...
nginx/noble-security 1.24.0-2ubuntu7.1 amd64 [upgradable from: 1.24.0-2ubuntu7]
vim/noble-updates 2:9.1.0016-1ubuntu7.5 amd64 [upgradable from: 2:9.1.0016-1ubuntu7.4]
libc6/noble 2.39-0ubuntu8.3 amd64 [upgradable from: 2.39-0ubuntu8.2]
N: There is 1 additional version.
"""

DNF_LIST = """kernel.x86_64                 5.14.0-503.el9    baseos
openssl.x86_64                3.2.2-6.el9_5     rhel-9-security
"""


def test_apt_listing_separates_security_updates():
    ups = _parse_apt_upgradable(APT_LIST)
    assert [u.name for u in ups] == ["nginx", "vim", "libc6"]
    assert ups[0].is_security is True          # noble-security
    assert ups[1].is_security is False         # noble-updates is not security
    assert ups[2].is_security is False
    assert ups[0].current_version == "1.24.0-2ubuntu7"
    assert ups[0].candidate_version == "1.24.0-2ubuntu7.1"
    assert ups[0].architecture == "amd64"


def test_apt_listing_ignores_noise_lines():
    assert _parse_apt_upgradable("Listing...\nN: hello\nWARNING: x\n\n") == []


def test_dnf_listing():
    ups = _parse_dnf_updates(DNF_LIST)
    assert [u.name for u in ups] == ["kernel", "openssl"]
    assert ups[0].architecture == "x86_64"
    assert ups[1].is_security is True
    assert ups[0].is_security is False


@pytest.mark.asyncio
async def test_apt_upgrade_cannot_hang_or_clobber_configs(driver, creds, fake_ssh):
    fake_ssh.single(ok("apt-get\n"), ok("done"))
    await driver.packages_upgrade(creds)
    argv = fake_ssh.sent()[-1].argv

    # debconf opens a dialog nobody can answer without this, and the
    # command then sits until the timeout.
    assert argv[:2] == ["env", "DEBIAN_FRONTEND=noninteractive"]
    assert "-y" in argv
    # Without both, a changed conffile either prompts (hang) or replaces a
    # file an administrator edited.
    assert "Dpkg::Options::=--force-confdef" in argv
    assert "Dpkg::Options::=--force-confold" in argv
    assert argv[-1] == "upgrade"
    assert fake_ssh.sent()[-1].become is True


@pytest.mark.asyncio
async def test_named_packages_use_only_upgrade(driver, creds, fake_ssh):
    """`apt-get install nginx` would happily install something not present;
    --only-upgrade keeps it to what is already there."""
    fake_ssh.single(ok("apt-get\n"), ok("done"))
    await driver.packages_upgrade(creds, names=["nginx", "vim"])
    argv = fake_ssh.sent()[-1].argv
    assert argv[-4:] == ["install", "--only-upgrade", "nginx", "vim"]


@pytest.mark.asyncio
async def test_rejects_malformed_package_names(driver, creds, fake_ssh):
    fake_ssh.single(ok("apt-get\n"))
    for bad in ("nginx; rm -rf /", "../etc", "ngin x", ""):
        with pytest.raises(UnsupportedOperation):
            await driver.packages_upgrade(creds, names=[bad])


@pytest.mark.asyncio
async def test_apt_says_so_rather_than_pretending_security_only_works(
    driver, creds, fake_ssh
):
    """apt has no --security flag. Silently upgrading everything when the
    caller asked for security only would be the worst possible answer."""
    fake_ssh.single(ok("apt-get\n"))
    with pytest.raises(UnsupportedOperation, match="unattended-upgrades"):
        await driver.packages_upgrade(creds, security_only=True)


@pytest.mark.asyncio
async def test_dnf_supports_security_only(driver, creds, fake_ssh):
    fake_ssh.single(ok("dnf\n"), ok("done"))
    await driver.packages_upgrade(creds, security_only=True)
    assert "--security" in fake_ssh.sent()[-1].argv


@pytest.mark.asyncio
async def test_unknown_package_manager_is_named(driver, creds, fake_ssh):
    fake_ssh.single(ok("unknown\n"))
    with pytest.raises(UnsupportedOperation, match="unknown"):
        await driver.packages_upgrade(creds)


@pytest.mark.asyncio
async def test_failed_upgrade_surfaces_the_tail_of_the_output(driver, creds, fake_ssh):
    fake_ssh.single(ok("apt-get\n"), fail("E: Unable to fetch some archives", rc=100))
    with pytest.raises(Exception, match="Unable to fetch"):
        await driver.packages_upgrade(creds)


@pytest.mark.asyncio
async def test_state_reports_reboot_required_and_security_count(
    driver, creds, fake_ssh
):
    fake_ssh.single(ok("apt-get\n"))          # manager detection
    fake_ssh.results(
        ok(APT_LIST),
        ok(),                                  # test -f reboot-required -> rc 0
        ok("linux-image-6.8.0-45-generic\ndbus\n"),
        fail("needs-restarting: not found", rc=127),
        ok("2026-07-30 21:00:00.000000000 +0400\n"),
    )
    state = await driver.packages_state(creds)
    assert state.manager == "apt"
    assert len(state.updates) == 3
    assert state.security_count == 1
    assert state.reboot_required is True
    assert state.reboot_required_by == ["linux-image-6.8.0-45-generic", "dbus"]
    assert state.last_refreshed_iso.startswith("2026-07-30")


@pytest.mark.asyncio
async def test_no_reboot_flag_means_no_reboot(driver, creds, fake_ssh):
    fake_ssh.single(ok("apt-get\n"))
    fake_ssh.results(ok(APT_LIST), fail("", rc=1), fail("", rc=1), fail("", rc=127), fail())
    state = await driver.packages_state(creds)
    assert state.reboot_required is False
    assert state.reboot_required_by == []


# ---------------- fleet caching ----------------


class _Device:
    """Just enough of the ORM row for the cache-writing path."""

    def __init__(self, name: str = "web-01") -> None:
        self.id = name
        self.name = name
        self.vendor = "linux"
        self.packages_manager = None
        self.packages_updates_count = None
        self.packages_security_count = None
        self.packages_reboot_required = False
        self.packages_checked_at = None
        self.packages_check_error = None


def test_apply_state_records_zero_as_zero_not_null():
    """A checked host with nothing pending must read as 0, and an unchecked
    one as null — the overview renders those differently on purpose."""
    from app.drivers.base import PackageState
    from app.services.packages import _apply_state

    d = _Device()
    assert d.packages_updates_count is None      # never checked

    _apply_state(d, PackageState(manager="apt", updates=[], security_count=0))
    assert d.packages_updates_count == 0
    assert d.packages_security_count == 0
    assert d.packages_checked_at is not None
    assert d.packages_check_error is None


def test_apply_state_clears_a_previous_error():
    from app.drivers.base import PackageState, PackageUpdate
    from app.services.packages import _apply_state

    d = _Device()
    d.packages_check_error = "could not connect"
    _apply_state(
        d,
        PackageState(
            manager="apt",
            updates=[PackageUpdate(name="nginx", is_security=True)],
            security_count=1,
            reboot_required=True,
        ),
    )
    assert d.packages_check_error is None
    assert d.packages_updates_count == 1
    assert d.packages_security_count == 1
    assert d.packages_reboot_required is True
