"""Audit log query — paginated + filterable, plus one sign-in session."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import Select, String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, require_admin, require_permission
from app.models.audit_log import AuditLog, AuditOutcome
from app.models.device import Device
from app.models.refresh_token import RefreshToken
from app.models.role import Role, RoleAssignment
from app.models.site import Site
from app.models.user import User
from app.schemas.audit import AuditLogEntry, AuditPage, AuditSessionDetail
from app.services import audit as audit_svc

router = APIRouter()

# The most entries one session view returns.
SESSION_ENTRY_LIMIT = 2000

_COLUMNS = (AuditLog, User.email, User.display_name, Device.name, Site.name)


def _with_names(stmt: Select[Any]) -> Select[Any]:
    return (
        stmt.outerjoin(User, User.id == AuditLog.user_id)
        .outerjoin(Device, Device.id == AuditLog.device_id)
        .outerjoin(Site, Site.id == AuditLog.site_id)
    )


def _entry(
    log: AuditLog,
    email: str | None,
    name: str | None,
    device: str | None,
    site: str | None,
) -> AuditLogEntry:
    return AuditLogEntry(
        id=log.id,
        ts=log.ts,
        user_id=log.user_id,
        user_email=email,
        user_name=name,
        section=log.section,
        action=log.action,
        outcome=log.outcome,
        device_id=log.device_id,
        device_name=device,
        site_id=log.site_id,
        site_name=site,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        request_payload=log.request_payload,
        response_meta=log.response_meta,
        error_message=log.error_message,
        session_id=log.session_id,
    )


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("", response_model=AuditPage)
async def query_audit(
    user: User = Depends(require_permission("audit", "read")),
    session: AsyncSession = Depends(db_session),
    *,
    user_id: UUID | None = Query(default=None),
    section: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=32),
    outcome: AuditOutcome | None = Query(default=None),
    device_id: UUID | None = Query(default=None),
    site_id: UUID | None = Query(default=None),
    session_id: UUID | None = Query(default=None),
    target: str | None = Query(default=None, max_length=200),
    search: str | None = Query(default=None, max_length=200),
    ts_from: datetime | None = Query(default=None),
    ts_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditPage:
    filters: list[Any] = [AuditLog.organization_id == user.organization_id]
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if section:
        # Substring match: "secret" finds secret.reveal and secret.rotate.
        filters.append(AuditLog.section.ilike(_like(section), escape="\\"))
    if action:
        filters.append(AuditLog.action == action)
    if outcome:
        filters.append(AuditLog.outcome == outcome)
    if device_id:
        filters.append(AuditLog.device_id == device_id)
    if site_id:
        filters.append(AuditLog.site_id == site_id)
    if session_id:
        filters.append(AuditLog.session_id == session_id)
    if target:
        t = _like(target)
        filters.append(
            or_(
                Device.name.ilike(t, escape="\\"),
                Site.name.ilike(t, escape="\\"),
                cast(AuditLog.device_id, String).ilike(t, escape="\\"),
            )
        )
    if search:
        q = _like(search)
        filters.append(
            or_(
                User.email.ilike(q, escape="\\"),
                User.display_name.ilike(q, escape="\\"),
                AuditLog.section.ilike(q, escape="\\"),
                AuditLog.action.ilike(q, escape="\\"),
                Device.name.ilike(q, escape="\\"),
                Site.name.ilike(q, escape="\\"),
                AuditLog.ip_address.ilike(q, escape="\\"),
            )
        )
    if ts_from:
        filters.append(AuditLog.ts >= ts_from)
    if ts_to:
        filters.append(AuditLog.ts <= ts_to)

    total = int(
        (
            await session.execute(_with_names(select(func.count(AuditLog.id))).where(*filters))
        ).scalar_one()
    )
    stmt = (
        _with_names(select(*_COLUMNS))
        .where(*filters)
        .order_by(AuditLog.ts.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    items = [_entry(*r) for r in rows]
    page_sessions = {e.session_id for e in items if e.session_id is not None}
    active: list[UUID] = []
    if page_sessions:
        active = list(
            (
                await session.execute(
                    select(RefreshToken.session_id)
                    .where(
                        RefreshToken.session_id.in_(page_sessions),
                        RefreshToken.revoked_at.is_(None),
                        RefreshToken.expires_at > datetime.now(UTC),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
    return AuditPage(
        items=items, total=total, limit=limit, offset=offset, active_session_ids=active
    )


@router.get("/sessions/{session_id}", response_model=AuditSessionDetail)
async def audit_session(
    session_id: UUID,
    user: User = Depends(require_permission("audit", "read")),
    session: AsyncSession = Depends(db_session),
) -> AuditSessionDetail:
    """Everything one sign-in session did, oldest first, with its metadata."""
    org = user.organization_id
    rows = (
        await session.execute(
            _with_names(select(*_COLUMNS))
            .where(AuditLog.organization_id == org, AuditLog.session_id == session_id)
            .order_by(AuditLog.ts.asc())
            .limit(SESSION_ENTRY_LIMIT)
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    entries = [_entry(*r) for r in rows]
    first, last = entries[0], entries[-1]
    login = next((e for e in entries if e.section == "auth" and e.action == "login"), None)
    method = (login.response_meta or {}).get("method") if login else None

    owner = await session.get(User, first.user_id) if first.user_id else None
    role: str | None = None
    if owner is not None:
        if owner.is_admin:
            role = "Admin"
        else:
            names = (
                (
                    await session.execute(
                        select(Role.name)
                        .join(RoleAssignment, RoleAssignment.role_id == Role.id)
                        .where(RoleAssignment.user_id == owner.id)
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
            role = ", ".join(sorted(names)) or None

    live = (
        await session.execute(
            select(RefreshToken.expires_at)
            .where(
                RefreshToken.session_id == session_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            )
            .order_by(RefreshToken.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    async def neighbour(older: bool) -> UUID | None:
        if first.user_id is None:
            return None
        return (
            await session.execute(
                select(AuditLog.session_id)
                .where(
                    AuditLog.organization_id == org,
                    AuditLog.user_id == first.user_id,
                    AuditLog.session_id.is_not(None),
                    AuditLog.session_id != session_id,
                    AuditLog.ts < first.ts if older else AuditLog.ts > last.ts,
                )
                .order_by(AuditLog.ts.desc() if older else AuditLog.ts.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

    return AuditSessionDetail(
        session_id=session_id,
        user_id=first.user_id,
        user_email=first.user_email,
        user_name=first.user_name,
        role=role,
        started_at=first.ts,
        last_activity_at=last.ts,
        sign_in_method=method,
        ip_address=(login or first).ip_address,
        user_agent=(login or first).user_agent,
        active=live is not None,
        expires_at=live,
        previous_session_id=await neighbour(True),
        next_session_id=await neighbour(False),
        entries=entries,
    )


@router.post("/sessions/{session_id}/revoke", status_code=204)
async def revoke_audit_session(
    session_id: UUID,
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
) -> None:
    """Admin only: end a sign-in session. Its refresh token stops working,
    so the session ends when its current access token expires."""
    tokens = (
        (
            await session.execute(
                select(RefreshToken)
                .join(User, User.id == RefreshToken.user_id)
                .where(
                    RefreshToken.session_id == session_id,
                    RefreshToken.revoked_at.is_(None),
                    User.organization_id == admin.organization_id,
                )
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(UTC)
    for rt in tokens:
        rt.revoked_at = now
    await audit_svc.write_audit(
        session,
        user_id=admin.id,
        organization_id=admin.organization_id,
        section="auth",
        action="session_revoke",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"session_id": str(session_id)},
        response_meta={"revoked_tokens": len(tokens)},
    )
    await session.commit()
