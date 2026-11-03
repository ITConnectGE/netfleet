"""Refresh-token rotation: a just-rotated token is not treated as theft.

Two tabs refreshing with the same cookie, or a lost response carrying the
new cookie, used to look like token replay and revoke every session —
the operator was bounced to /login. Within the grace window the old token
now yields a sibling; outside it, reuse still revokes everything.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.security import hash_refresh_token
from app.models.refresh_token import RefreshToken
from app.services import auth as auth_svc


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return iter(self._value if isinstance(self._value, list) else [self._value])


class FakeSession:
    def __init__(self, token: RefreshToken, user) -> None:
        self.token = token
        self.user = user
        self.added: list[RefreshToken] = []
        self.revoke_all_called = False

    async def execute(self, stmt):
        # _revoke_all_for_user selects by user_id; rotate selects by hash.
        if "revoked_at IS NULL" in str(stmt):
            self.revoke_all_called = True
            return _Result([t for t in [self.token, *self.added] if t.revoked_at is None])
        return _Result(self.token)

    async def get(self, _model, _id):
        return self.user

    def add(self, obj) -> None:
        obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _setup(*, revoked_ago: float | None, rotated: bool):
    raw = "presented-token"
    user = SimpleNamespace(id=uuid.uuid4(), is_active=True)
    now = datetime.now(UTC)
    token = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw),
        expires_at=now + timedelta(days=1),
        revoked_at=None if revoked_ago is None else now - timedelta(seconds=revoked_ago),
        replaced_by_id=uuid.uuid4() if rotated else None,
    )
    return raw, FakeSession(token, user)


async def _rotate(session: FakeSession, raw: str):
    return await auth_svc.rotate_refresh_token(
        session, presented_raw=raw, user_agent=None, ip_address=None
    )


@pytest.mark.asyncio
async def test_live_token_rotates():
    raw, session = _setup(revoked_ago=None, rotated=False)
    _, new_raw, _ = await _rotate(session, raw)
    assert new_raw != raw
    assert session.token.revoked_at is not None
    assert session.token.replaced_by_id == session.added[0].id


@pytest.mark.asyncio
async def test_just_rotated_token_gets_a_sibling_not_a_lockout():
    raw, session = _setup(revoked_ago=5, rotated=True)
    revoked_at = session.token.revoked_at
    _, new_raw, _ = await _rotate(session, raw)
    assert new_raw
    assert not session.revoke_all_called
    # The grace window is measured from the first rotation, never extended.
    assert session.token.revoked_at == revoked_at


@pytest.mark.asyncio
async def test_old_rotated_token_still_trips_reuse_detection():
    raw, session = _setup(
        revoked_ago=auth_svc.REFRESH_REUSE_GRACE_SECONDS + 30, rotated=True
    )
    with pytest.raises(auth_svc.AuthError, match="reuse detected"):
        await _rotate(session, raw)
    assert session.revoke_all_called


@pytest.mark.asyncio
async def test_logged_out_token_is_rejected_without_revoking_everything():
    raw, session = _setup(revoked_ago=5, rotated=False)
    with pytest.raises(auth_svc.AuthError, match="revoked"):
        await _rotate(session, raw)
    assert not session.revoke_all_called
