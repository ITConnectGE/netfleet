"""Common FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Awaitable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_jwt
from app.models.user import User
from app.services import rbac

# Lazy bearer scheme — auto_error=False lets us return a uniform 401 below
_bearer = HTTPBearer(auto_error=False)


async def db_session() -> AsyncIterator[AsyncSession]:
    async for s in get_session():
        yield s


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(db_session),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_jwt(creds.credentials, expected_type="access")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    user = (
        await session.execute(select(User).where(User.id == payload["sub"], User.is_active.is_(True)))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")

    # Stash for downstream audit logging
    request.state.user = user
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin only")
    return user


ScopeResolver = Callable[[Request], Awaitable[tuple[UUID | None, UUID | None]]]


def require_permission(
    section: str,
    action: str,
    *,
    scope: ScopeResolver | None = None,
) -> Callable:
    """Dependency factory that enforces RBAC for (section, action).

    `scope` is an optional async function that returns (site_id, device_id) for
    this request — used by per-device or per-site endpoints. If not given, the
    check is org-scoped only.
    """

    async def _dep(
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(db_session),
    ) -> User:
        site_id: UUID | None = None
        device_id: UUID | None = None
        if scope is not None:
            site_id, device_id = await scope(request)
        try:
            await rbac.require(
                session, user, section, action, site_id=site_id, device_id=device_id
            )
        except PermissionError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
        return user

    return _dep


def client_ip(request: Request) -> str | None:
    """Best-effort client IP from forwarded headers (Caddy sets X-Real-IP / X-Forwarded-For)."""
    fwd = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
