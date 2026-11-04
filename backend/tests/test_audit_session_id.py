"""Audit rows carry the sign-in session of the request that wrote them."""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import pytest

from app.core.request_context import current_session_id
from app.core.security import decode_jwt
from app.services import audit as audit_svc
from app.services import auth as auth_svc


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


class _User:
    def __init__(self) -> None:
        self.id = uuid4()
        self.organization_id = uuid4()
        self.is_admin = False
        self.last_login_at = None


async def _isolated(coro: Coroutine[Any, Any, None]) -> None:
    """Run in a fresh context, as each HTTP request does."""
    await asyncio.create_task(coro, context=contextvars.Context())


async def _write(session: _FakeSession, **kw: object) -> None:
    await audit_svc.write_audit(
        session, user_id=None, organization_id=None, section="x", action="y", **kw
    )


@pytest.mark.asyncio
async def test_audit_row_takes_the_current_session() -> None:
    sid = uuid4()

    async def run() -> None:
        current_session_id.set(sid)
        s = _FakeSession()
        await _write(s)
        assert s.added[0].session_id == sid

    await _isolated(run())


@pytest.mark.asyncio
async def test_background_audit_rows_have_no_session() -> None:
    async def run() -> None:
        s = _FakeSession()
        await _write(s)
        assert s.added[0].session_id is None

    await _isolated(run())


@pytest.mark.asyncio
async def test_login_session_reaches_refresh_token_access_token_and_audit() -> None:
    async def run() -> None:
        s = _FakeSession()
        user = _User()
        await auth_svc.issue_refresh_token(s, user=user, user_agent=None, ip_address=None)
        rt = s.added[0]
        assert rt.session_id is not None
        access, _ = auth_svc.issue_access_token(user)
        assert decode_jwt(access)["sid"] == str(rt.session_id)
        await _write(s)
        assert s.added[1].session_id == rt.session_id

    await _isolated(run())


@pytest.mark.asyncio
async def test_password_change_keeps_the_session() -> None:
    sid = uuid4()

    async def run() -> None:
        s = _FakeSession()
        await auth_svc.issue_refresh_token(
            s, user=_User(), user_agent=None, ip_address=None, session_id=sid
        )
        assert s.added[0].session_id == sid
        assert current_session_id.get() == sid

    await _isolated(run())
