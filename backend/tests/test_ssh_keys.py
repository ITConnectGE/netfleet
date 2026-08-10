"""Writing keys into a remote `authorized_keys`.

Two failure modes drive everything here. A key line containing a newline
appends a *second*, caller-chosen key — quoting does not stop that, so the
content is validated rather than trusted. And sshd ignores an authorized_keys
whose modes or ownership it dislikes **silently**: no error to the client,
nothing in the log at default verbosity, just a key that does not work.
"""

from __future__ import annotations

import pytest

from app.drivers.base import UnsupportedOperation
from app.drivers.linux import (
    _AUTHORIZED_KEYS_APPEND,
    _AUTHORIZED_KEYS_REMOVE,
    _assert_safe_public_key,
    _parse_authorized_keys,
)
from app.services.ssh_keys import (
    fingerprint_from_public_openssh,
    generate_ed25519_keypair,
    key_blob,
    public_key_from_private_pem,
)

from helpers import ok

ED = (
    "ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIJH0kK7VvE0v9pFHZ3q0N8yQ1p2W4pKZ8pF5nQ9mZ1aB"
)


# ---------------- validating what gets written ----------------


def test_a_plain_key_is_accepted():
    assert _assert_safe_public_key(f"{ED} netfleet-abc") == f"{ED} netfleet-abc"


def test_a_newline_in_a_key_is_refused():
    """The attack that matters: quoting does not stop a newline, and the line
    after it becomes a second authorized key."""
    with pytest.raises(ValueError, match="line breaks"):
        _assert_safe_public_key(f"{ED} ok\nssh-rsa AAAAB3Nza attacker")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "not-a-key",
        "ssh-ed25519",                       # no body
        f"ssh-magic {ED.split()[1]}",        # unknown type
        "ssh-ed25519 not-base64!!",
    ],
)
def test_malformed_keys_are_refused(value):
    with pytest.raises(ValueError):
        _assert_safe_public_key(value)


def test_restricted_keys_keep_their_options():
    """An operator pasting a `command=` key means it. Dropping the options
    would silently turn a restricted key into a full shell key."""
    line = f'command="/usr/bin/backup",no-pty {ED} restricted'
    assert _assert_safe_public_key(line) == line
    parsed = _parse_authorized_keys(line)[0]
    assert parsed.options == 'command="/usr/bin/backup",no-pty'
    assert parsed.comment == "restricted"


# ---------------- reading them back ----------------


def test_parsing_skips_comments_and_blanks():
    keys = _parse_authorized_keys(f"# a comment\n\n{ED} mine\n")
    assert len(keys) == 1
    assert keys[0].comment == "mine"
    assert keys[0].key_type == "ssh-ed25519"


def test_netfleets_own_key_is_flagged():
    """The per-user endpoint refuses to remove it — that is the rotation
    endpoint's job, which proves the replacement first."""
    keys = _parse_authorized_keys(
        f"{ED} netfleet-0f8e7d6c-1234-5678-9abc-def012345678\n{ED} someone-else\n"
    )
    assert keys[0].is_netfleet is True
    assert keys[1].is_netfleet is False


def test_a_fingerprint_is_derived_for_display():
    keys = _parse_authorized_keys(f"{ED} mine")
    assert keys[0].fingerprint is not None
    assert keys[0].fingerprint.startswith("SHA256:")


def test_a_key_with_no_comment_still_parses():
    keys = _parse_authorized_keys(ED)
    assert len(keys) == 1
    assert keys[0].comment is None


# ---------------- the remote scripts ----------------


def test_append_fixes_the_modes_sshd_cares_about():
    """sshd ignores an authorized_keys that is too open, and says nothing at
    all about it. Every write sets these rather than assuming."""
    assert "chmod 700" in _AUTHORIZED_KEYS_APPEND
    assert "chmod 600" in _AUTHORIZED_KEYS_APPEND
    assert "chown -R" in _AUTHORIZED_KEYS_APPEND


def test_append_guards_against_a_missing_trailing_newline():
    """Otherwise the new key is concatenated onto the last one and neither
    works."""
    assert 'tail -c 1 "$f"' in _AUTHORIZED_KEYS_APPEND


def test_scripts_take_the_home_directory_from_getent():
    """`~user` is shell expansion, and the account may have a home outside
    /home. getent is the answer the system itself gives."""
    for script in (_AUTHORIZED_KEYS_APPEND, _AUTHORIZED_KEYS_REMOVE):
        assert "getent passwd" in script


def test_remove_preserves_the_file_rather_than_replacing_it():
    """`mv` would give the file the temp file's ownership and mode, which is
    the same silent-failure trap from the other direction."""
    assert 'cat "$tmp" > "$f"' in _AUTHORIZED_KEYS_REMOVE
    assert "mv " not in _AUTHORIZED_KEYS_REMOVE


def test_remove_matches_on_the_key_body():
    """Comments do not identify a key: during a rotation two NetFleet keys
    carry the same one, so matching on comments removes the wrong key or
    both."""
    assert "-v b=" in _AUTHORIZED_KEYS_REMOVE


@pytest.mark.asyncio
async def test_key_writes_are_escalated(driver, creds, fake_ssh):
    fake_ssh.single(ok(""), ok(""))
    await driver.authorized_key_add(
        creds, username="deploy", public_key=f"{ED} mine"
    )
    await driver.authorized_key_remove(
        creds, username="deploy", blob=ED.split()[1]
    )
    assert all(c.become for c in fake_ssh.sent())


@pytest.mark.asyncio
async def test_the_key_travels_on_stdin_not_in_the_command(
    driver, creds, fake_ssh
):
    """The script is a constant; every caller-supplied value arrives as a
    positional argument or on stdin, so nothing is ever spliced into the text
    of a shell command."""
    fake_ssh.single(ok(""))
    await driver.authorized_key_add(
        creds, username="deploy", public_key=f"{ED} mine"
    )
    sent = fake_ssh.sent()[0]
    assert "mine" not in " ".join(sent.argv)
    assert sent.argv[-1] == "deploy"


@pytest.mark.asyncio
async def test_a_bad_username_never_reaches_the_host(driver, creds, fake_ssh):
    """Rejected before any command is issued, by the same account-name rule
    the host-accounts feature already uses."""
    with pytest.raises(UnsupportedOperation):
        await driver.authorized_key_add(
            creds, username="root; rm -rf /", public_key=f"{ED} x"
        )
    assert fake_ssh.sent() == []


# ---------------- key identity ----------------


def test_the_blob_identifies_a_key_and_the_comment_does_not():
    """Two keys generated a moment apart share a comment and differ only in
    the body — which is exactly the situation mid-rotation."""
    a = generate_ed25519_keypair(comment="netfleet")
    b = generate_ed25519_keypair(comment="netfleet")
    ka = public_key_from_private_pem(a.private_pem, comment="netfleet-dev")
    kb = public_key_from_private_pem(b.private_pem, comment="netfleet-dev")
    assert ka.split()[-1] == kb.split()[-1]      # same comment
    assert key_blob(ka) != key_blob(kb)          # different key


def test_fingerprints_match_the_openssh_format():
    pair = generate_ed25519_keypair()
    fp = fingerprint_from_public_openssh(pair.public_openssh)
    assert fp.startswith("SHA256:")
    assert "=" not in fp                          # padding stripped, as ssh does


def test_key_blob_refuses_a_non_key():
    with pytest.raises(ValueError):
        key_blob("nonsense")
