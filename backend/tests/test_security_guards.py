"""Regression tests for the 2026-11 security audit fixes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pyotp
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import users as users_api
from app.core.security import encrypt_field
from app.drivers import linux
from app.schemas.device_ops import (
    BulkPasswordResetRequest,
    DeviceUserCreate,
    DeviceUserPasswordReset,
)
from app.schemas.user import UserCreate, UserUpdate
from app.services import auth as auth_svc

# ---------------- TOTP brute force / replay ----------------


class _Result:
    def __init__(self, v):
        self._v = v

    def scalar_one_or_none(self):
        return self._v


class _TotpSession:
    def __init__(self, user):
        self.user = user

    async def execute(self, _stmt):
        return _Result(self.user)

    async def flush(self):
        return None


def _totp_user():
    secret = pyotp.random_base32()
    user = SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        is_active=True,
        totp_enrolled=True,
        totp_secret_encrypted=encrypt_field(secret),
        totp_failed_attempts=0,
        totp_locked_until=None,
        totp_last_step=None,
    )
    return user, secret


def _temp_token(user) -> str:
    return auth_svc.issue_mfa_temp_token_for_id(str(user.id), str(user.organization_id))[0]


async def _verify(session, user, code):
    return await auth_svc.verify_totp_for_user(
        session, mfa_temp_token=_temp_token(user), code=code
    )


def _wrong(secret: str) -> str:
    good = {pyotp.TOTP(secret).at(datetime.now(UTC), o) for o in (-1, 0, 1)}
    return next(c for c in (f"{n:06d}" for n in range(10**6)) if c not in good)


async def test_totp_locks_after_five_wrong_codes():
    user, secret = _totp_user()
    s = _TotpSession(user)
    for _ in range(auth_svc.TOTP_MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth_svc.AuthError, match="invalid"):
            await _verify(s, user, _wrong(secret))
    assert user.totp_locked_until is not None
    # Even the right code is refused while locked.
    with pytest.raises(auth_svc.AuthError, match="too many"):
        await _verify(s, user, pyotp.TOTP(secret).now())


async def test_totp_code_cannot_be_replayed():
    user, secret = _totp_user()
    s = _TotpSession(user)
    code = pyotp.TOTP(secret).now()
    await _verify(s, user, code)
    assert user.totp_last_step is not None
    with pytest.raises(auth_svc.AuthError, match="already used"):
        await _verify(s, user, code)


async def test_totp_success_resets_counter():
    user, secret = _totp_user()
    s = _TotpSession(user)
    with pytest.raises(auth_svc.AuthError):
        await _verify(s, user, _wrong(secret))
    assert user.totp_failed_attempts == 1
    await _verify(s, user, pyotp.TOTP(secret).now())
    assert user.totp_failed_attempts == 0


async def test_expired_lock_lets_user_in_again():
    user, secret = _totp_user()
    user.totp_locked_until = datetime.now(UTC) - timedelta(seconds=1)
    await _verify(_TotpSession(user), user, pyotp.TOTP(secret).now())
    assert user.totp_locked_until is None


# ---------------- newline injection into chpasswd ----------------


@pytest.mark.parametrize("bad", ["Passw0rd!\nroot:Attacker123", "abcdefgh\r", "abc\x00defgh"])
def test_device_password_schemas_refuse_control_chars(bad):
    with pytest.raises(ValidationError):
        DeviceUserPasswordReset(new_password=bad)
    with pytest.raises(ValidationError):
        DeviceUserCreate(username="alice", password=bad)
    with pytest.raises(ValidationError):
        BulkPasswordResetRequest(device_ids=[uuid.uuid4()], username="alice", new_password=bad)


def test_device_password_schema_accepts_normal_password():
    assert DeviceUserPasswordReset(new_password="C0rrect horse: battery!").new_password


def test_chpasswd_refuses_record_injection():
    with pytest.raises(ValueError):
        linux._chpasswd("alice", "x\nroot:pwned")
    with pytest.raises(ValueError):
        linux._chpasswd("root:x\nalice", "pw")
    assert linux._chpasswd("alice", "a:b c").stdin == "alice:a:b c\n"


# ---------------- users:write cannot reach super-admin ----------------


def _actor(is_admin: bool):
    return SimpleNamespace(id=uuid.uuid4(), organization_id=uuid.uuid4(), is_admin=is_admin)


async def test_non_admin_cannot_create_super_admin():
    payload = UserCreate(email="x@example.com", display_name="x", is_admin=True)
    with pytest.raises(HTTPException) as e:
        await users_api.create_user(payload, SimpleNamespace(), _actor(False), None)
    assert e.value.status_code == 403


async def test_non_admin_cannot_promote_anyone():
    with pytest.raises(HTTPException) as e:
        await users_api.update_user(
            uuid.uuid4(), UserUpdate(is_admin=True), SimpleNamespace(), _actor(False), None
        )
    assert e.value.status_code == 403


async def test_non_admin_cannot_touch_admin_account(monkeypatch):
    async def fake_get_user(_s, _org, _uid):
        return SimpleNamespace(is_admin=True)

    monkeypatch.setattr(users_api.user_svc, "get_user", fake_get_user)
    with pytest.raises(HTTPException) as e:
        await users_api._guard_admin_target(None, _actor(False), uuid.uuid4())
    assert e.value.status_code == 403
    # A super-admin may.
    await users_api._guard_admin_target(None, _actor(True), uuid.uuid4())
