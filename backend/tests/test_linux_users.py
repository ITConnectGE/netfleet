"""Account and group management on a Linux host.

The safety rules get more attention than the happy path here: a wrong
`usermod --lock` is how a managed host stops being manageable.
"""

from __future__ import annotations

import pytest

from app.drivers import ssh_transport as ssh
from app.drivers.base import UnsupportedOperation
from helpers import fail, ok

PASSWD = """root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
netfleet:x:1001:1001:NetFleet management:/home/netfleet:/bin/bash
deploy:x:1002:1002:Deploy bot,,,:/home/deploy:/bin/bash
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
"""
GROUP = """root:x:0:
sudo:x:27:netfleet,deploy
netfleet:x:1001:
deploy:x:1002:
docker:x:998:deploy
"""
STATUS = """root L 2026-01-01 0 99999 7 -1
netfleet L 2026-07-01 0 99999 7 -1
deploy P 2026-07-20 0 99999 7 -1
"""
LASTLOG = """Username         Port     From             Latest
root             pts/0    10.0.0.9         Wed Jul 29 21:03:11 +0400 2026
deploy                                     **Never logged in**
"""


@pytest.mark.asyncio
async def test_lists_accounts_with_groups_and_flags(driver, creds, fake_ssh):
    fake_ssh.results(ok(PASSWD), ok(GROUP), ok(STATUS), ok(LASTLOG))
    users = await driver.device_users_list(creds)
    by_name = {u.name: u for u in users}

    deploy = by_name["deploy"]
    assert deploy.uid == 1002
    assert deploy.group == "deploy"
    assert set(deploy.groups) == {"deploy", "sudo", "docker"}
    assert deploy.shell == "/bin/bash"
    assert deploy.comment == "Deploy bot"        # GECOS trailing commas dropped
    assert deploy.disabled is False              # status P
    assert deploy.is_system is False
    assert deploy.is_protected is False

    # Ordering puts real accounts first — the system ones are noise.
    assert [u.name for u in users][:2] == ["deploy", "netfleet"]


@pytest.mark.asyncio
async def test_marks_system_and_protected_accounts(driver, creds, fake_ssh):
    fake_ssh.results(ok(PASSWD), ok(GROUP), ok(STATUS), ok(LASTLOG))
    by_name = {u.name: u for u in await driver.device_users_list(creds)}

    assert by_name["root"].is_system and by_name["root"].is_protected
    assert by_name["daemon"].is_system
    assert by_name["nobody"].is_system, "65534 is the nobody UID, not a real user"
    # The account NetFleet connects as is protected even though it is a
    # perfectly ordinary UID.
    assert by_name["netfleet"].is_system is False
    assert by_name["netfleet"].is_protected is True


@pytest.mark.asyncio
async def test_locked_state_comes_from_passwd_status(driver, creds, fake_ssh):
    fake_ssh.results(ok(PASSWD), ok(GROUP), ok(STATUS), ok(LASTLOG))
    by_name = {u.name: u for u in await driver.device_users_list(creds)}
    assert by_name["netfleet"].disabled is True     # L
    assert by_name["deploy"].disabled is False      # P


@pytest.mark.asyncio
async def test_survives_passwd_status_needing_root(driver, creds, fake_ssh):
    # Without sudo `passwd -Sa` fails; the list must still render.
    fake_ssh.results(ok(PASSWD), ok(GROUP), fail("permission denied"), fail())
    users = await driver.device_users_list(creds)
    assert len(users) == 5
    assert all(u.disabled is False for u in users)


@pytest.mark.asyncio
async def test_refuses_to_touch_root_or_the_management_account(driver, creds, fake_ssh):
    for target in ("root", "netfleet"):
        with pytest.raises(UnsupportedOperation):
            await driver.device_user_set_disabled(creds, target, True)
        with pytest.raises(UnsupportedOperation):
            await driver.device_user_remove(creds, target)
        with pytest.raises(UnsupportedOperation):
            await driver.device_user_set_password(creds, target, "x")
    assert fake_ssh.sent() == [], "nothing should have reached the host"


@pytest.mark.asyncio
async def test_group_membership_is_allowed_on_the_management_account(
    driver, creds, fake_ssh
):
    # Adding a group cannot take away access, so unlike locking it is fine.
    await driver.device_user_set_groups(creds, "netfleet", ["sudo", "docker"])
    assert fake_ssh.sent()[0].argv == [
        "usermod", "--groups", "sudo,docker", "netfleet",
    ]


@pytest.mark.asyncio
async def test_rejects_malformed_account_names(driver, creds, fake_ssh):
    for bad in ("Deploy", "de ploy", "deploy;rm -rf /", "1deploy", "a" * 33, ""):
        with pytest.raises(UnsupportedOperation):
            await driver.device_user_add(creds, username=bad)
    assert fake_ssh.sent() == []


@pytest.mark.asyncio
async def test_creates_account_and_sets_password_off_the_command_line(
    driver, creds, fake_ssh
):
    await driver.device_user_add(
        creds, username="deploy", password="s3cret", groups=["sudo"],
        comment="Deploy bot, second shift",
    )
    useradd, chpasswd = fake_ssh.sent()
    assert useradd.argv[0] == "useradd" and useradd.become
    assert "--create-home" in useradd.argv
    assert useradd.argv[useradd.argv.index("--groups") + 1] == "sudo"
    # A comma in GECOS would silently become the next field.
    assert "," not in useradd.argv[useradd.argv.index("--comment") + 1]
    assert useradd.argv[-1] == "deploy"

    # The password must never appear in argv, where /proc exposes it to
    # every process on the host.
    assert chpasswd.argv == ["chpasswd"]
    assert chpasswd.stdin == "deploy:s3cret\n"
    assert "s3cret" not in " ".join(useradd.argv)


@pytest.mark.asyncio
async def test_account_without_password_is_left_locked(driver, creds, fake_ssh):
    await driver.device_user_add(creds, username="svc", create_home=False)
    argvs = [c.argv for c in fake_ssh.sent()]
    assert ["usermod", "--lock", "svc"] in argvs
    assert "--no-create-home" in argvs[0]


@pytest.mark.asyncio
async def test_delete_only_removes_home_when_asked(driver, creds, fake_ssh):
    await driver.device_user_remove(creds, "deploy")
    assert fake_ssh.sent()[-1].argv == ["userdel", "deploy"]
    await driver.device_user_remove(creds, "deploy", remove_home=True)
    assert fake_ssh.sent()[-1].argv == ["userdel", "--remove", "deploy"]


@pytest.mark.asyncio
async def test_refuses_to_delete_system_groups(driver, creds, fake_ssh):
    for g in ("sudo", "root", "wheel"):
        with pytest.raises(UnsupportedOperation):
            await driver.device_group_remove(creds, g)
    await driver.device_group_remove(creds, "deploy")
    assert fake_ssh.sent()[-1].argv == ["groupdel", "deploy"]


@pytest.mark.asyncio
async def test_lists_groups_with_members(driver, creds, fake_ssh):
    fake_ssh.single(ok(GROUP))
    groups = {g.name: g for g in await driver.device_groups_list(creds)}
    assert groups["sudo"].members == ["netfleet", "deploy"]
    assert groups["sudo"].is_system is True      # gid 27
    assert groups["deploy"].is_system is False   # gid 1002


@pytest.mark.asyncio
async def test_surfaces_a_failed_command(driver, creds, fake_ssh):
    fake_ssh.single(fail("useradd: user 'deploy' already exists"))
    with pytest.raises(ssh.SshError, match="already exists"):
        await driver.device_user_set_disabled(creds, "deploy", True)
