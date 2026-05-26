"""Audit log query — paginated + filterable."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import db_session, require_permission
from app.models.audit_log import AuditLog, AuditOutcome
from app.models.user import User
from app.schemas.audit import AuditLogEntry, AuditPage

router = APIRouter()


@router.get("", response_model=AuditPage)
async def query_audit(
    user: User = Depends(require_permission("audit", "read")),
    session: AsyncSession = Depends(db_session),
    *,
    user_id: UUID | None = Query(default=None),
    section: str | None = Query(default=None),
    action: str | None = Query(default=None),
    outcome: AuditOutcome | None = Query(default=None),
    device_id: UUID | None = Query(default=None),
    site_id: UUID | None = Query(default=None),
    ts_from: datetime | None = Query(default=None),
    ts_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AuditPage:
    filters = [AuditLog.organization_id == user.organization_id]
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if section:
        filters.append(AuditLog.section == section)
    if action:
        filters.append(AuditLog.action == action)
    if outcome:
        filters.append(AuditLog.outcome == outcome)
    if device_id:
        filters.append(AuditLog.device_id == device_id)
    if site_id:
        filters.append(AuditLog.site_id == site_id)
    if ts_from:
        filters.append(AuditLog.ts >= ts_from)
    if ts_to:
        filters.append(AuditLog.ts <= ts_to)

    total = int(
        (await session.execute(select(func.count(AuditLog.id)).where(*filters))).scalar_one()
    )

    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(*filters)
        .order_by(AuditLog.ts.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        AuditLogEntry(
            id=log.id,
            ts=log.ts,
            user_id=log.user_id,
            user_email=email,
            section=log.section,
            action=log.action,
            outcome=log.outcome,
            device_id=log.device_id,
            site_id=log.site_id,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            request_payload=log.request_payload,
            response_meta=log.response_meta,
            error_message=log.error_message,
        )
        for log, email in rows
    ]
    return AuditPage(items=items, total=total, limit=limit, offset=offset)
