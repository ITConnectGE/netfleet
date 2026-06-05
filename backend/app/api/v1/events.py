"""Central log-event endpoints — the syslog-style cross-device inbox."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.models.audit_log import AuditOutcome
from app.models.device_log_event import EventSeverity
from app.models.user import User
from app.schemas.events import (
    EventAcknowledgeRequest,
    EventListResponse,
    EventPublic,
)
from app.services import audit as audit_svc
from app.services import events as events_svc

router = APIRouter()


@router.get("", response_model=EventListResponse)
async def list_events(
    severity: list[EventSeverity] | None = Query(default=None),
    device_id: UUID | None = Query(default=None),
    tenant_id: UUID | None = Query(default=None),
    site_id: UUID | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_permission("events", "read")),
    session: AsyncSession = Depends(db_session),
) -> EventListResponse:
    rows, total, unack, by_severity = await events_svc.list_events(
        session,
        user.organization_id,
        severities=severity,
        device_id=device_id,
        tenant_id=tenant_id,
        site_id=site_id,
        acknowledged=acknowledged,
        since=since,
        until=until,
        search=search,
        limit=limit,
        offset=offset,
    )
    return EventListResponse(
        rows=[EventPublic(**r) for r in rows],
        total=total,
        unacknowledged_total=unack,
        by_severity=by_severity,
    )


@router.post("/acknowledge", status_code=204)
async def acknowledge_events(
    payload: EventAcknowledgeRequest,
    request: Request,
    user: User = Depends(require_permission("events", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    updated = await events_svc.acknowledge_events(
        session,
        user.organization_id,
        event_ids=payload.ids,
        user_id=user.id,
    )
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="events",
        action="acknowledge",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"ids": [str(i) for i in payload.ids]},
        response_meta={"updated": updated},
    )
    await session.commit()


@router.get("/summary")
async def events_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, int | dict[str, int]]:
    """Cheap header-badge query — only the unack totals + by-severity break-down."""
    _, _, unack, by_severity = await events_svc.list_events(
        session, user.organization_id, limit=1, offset=0
    )
    return {"unacknowledged_total": unack, "by_severity": by_severity}


@router.get("/per-site-summary")
async def events_per_site_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> dict[str, dict[str, int]]:
    """Unacknowledged severity counts grouped by site_id. Used by the
    fleet map to colour a site's pin dark-red when there's any
    critical-severity unacknowledged event hanging on a device that
    belongs to it. Returns `{site_id_str: {severity: count}}`."""
    rows = await events_svc.per_site_unack_summary(session, user.organization_id)
    return rows
