"""Refresh-token rotation: a just-rotated token is not treated as theft,
but cannot outlive a revoked session either.

Two tabs refreshing with the same cookie, or a lost response carrying the
new cookie, used to look like token replay and revoke every session —
the operator was bounced to /login. Within the grace window the old token
now yields a sibling, but only while the newest token of its chain is
still live: logout and revoke-all (password change, reuse detection) must
not be undone by presenting a recently rotated ancestor.
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
        return iter(self._value)


class FakeSession:
    """Just enough AsyncSession for rotate_refresh_token and
    _revoke_all_for_user, over an in-memory token table."""

    def __init__(self, user) -> None:
        self.user = user
        self.tokens: dict[uuid.UUID, RefreshToken] = {}
        self.revoke_all_called = False
        self.presented: RefreshToken | None = None

    def put(self, token: RefreshToken) -> RefreshToken:
        if token.id is None:
            token.id = uuid.uuid4()
        self.tokens[token.id] = token
        return token

    async def execute(self, stmt):
        # _revoke_all_for_user selects the user's live tokens; rotate and
        # revoke look up the presented token by hash.
        if "revoked_at IS NULL" in str(stmt):
            self.revoke_all_called = True
            return _Result([t for t in self.tokens.values() if t.revoked_at is None])
        return _Result(self.presented)

    async def get(self, model, ident):
        if model is RefreshToken:
            return self.tokens.get(ident)
        return self.user

    def add(self, obj) -> None:
        self.put(obj)

    async def flush(self) -> None:
        return None


NOW = datetime.now(UTC)
RAW = "presented-token"


def _token(session: FakeSession, *, raw: str | None = None, revoked_ago=None,
           successor: RefreshToken | None = None, expires_in=timedelta(days=1)):
    return session.put(
        RefreshToken(
            user_id=session.user.id,
            token_hash=hash_refresh_token(raw or uuid.uuid4().hex),
            expires_at=NOW + expires_in,
            revoked_at=None if revoked_ago is None else NOW - timedelta(seconds=revoked_ago),
            replaced_by_id=successor.id if successor else None,
        )
    )


def _session() -> FakeSession:
    return FakeSession(SimpleNamespace(id=uuid.uuid4(), is_active=True))


async def _rotate(session: FakeSession, presented: RefreshToken):
    session.presented = presented
    return await auth_svc.rotate_refresh_token(
        session, presented_raw=RAW, user_agent=None, ip_address=None
    )


async def test_live_token_rotates():
    s = _session()
    tok = _token(s, raw=RAW)
    _, new_raw, _ = await _rotate(s, tok)
    assert new_raw != RAW
    assert tok.revoked_at is not None
    assert tok.replaced_by_id is not None
    assert s.tokens[tok.replaced_by_id].revoked_at is None


async def test_just_rotated_token_with_live_successor_gets_a_sibling():
    s = _session()
    child = _token(s)
    parent = _token(s, raw=RAW, revoked_ago=5, successor=child)
    revoked_at = parent.revoked_at
    _, new_raw, expires = await _rotate(s, parent)
    assert new_raw
    assert not s.revoke_all_called
    # The grace window is measured from the first rotation, never extended,
    # and the sibling never outlives its parent.
    assert parent.revoked_at == revoked_at
    assert expires <= parent.expires_at


async def test_grace_follows_multi_hop_chain_to_live_tip():
    s = _session()
    tip = _token(s)
    mid = _token(s, revoked_ago=2, successor=tip)
    parent = _token(s, raw=RAW, revoked_ago=5, successor=mid)
    _, new_raw, _ = await _rotate(s, parent)
    assert new_raw


async def test_password_change_is_not_undone_by_recently_rotated_ancestor():
    s = _session()
    child = _token(s)
    parent = _token(s, raw=RAW, revoked_ago=5, successor=child)
    # Password change / reuse detection: every live token revoked, with no
    # successor.
    await auth_svc._revoke_all_for_user(s, s.user.id)
    assert child.revoked_at is not None
    with pytest.raises(auth_svc.AuthError, match="revoked"):
        await _rotate(s, parent)
    assert len(s.tokens) == 2  # nothing new minted


async def test_revoked_tip_two_hops_away_still_blocks_grace():
    s = _session()
    tip = _token(s, revoked_ago=1)  # logged out / revoked-all
    mid = _token(s, revoked_ago=2, successor=tip)
    parent = _token(s, raw=RAW, revoked_ago=5, successor=mid)
    with pytest.raises(auth_svc.AuthError, match="revoked"):
        await _rotate(s, parent)


async def test_old_rotated_token_still_trips_reuse_detection():
    s = _session()
    child = _token(s)
    parent = _token(
        s, raw=RAW, revoked_ago=auth_svc.REFRESH_REUSE_GRACE_SECONDS + 30, successor=child
    )
    with pytest.raises(auth_svc.AuthError, match="reuse detected"):
        await _rotate(s, parent)
    assert s.revoke_all_called
    assert child.revoked_at is not None


async def test_logged_out_token_is_rejected_without_revoking_everything():
    s = _session()
    tok = _token(s, raw=RAW, revoked_ago=5)
    with pytest.raises(auth_svc.AuthError, match="revoked"):
        await _rotate(s, tok)
    assert not s.revoke_all_called
