"""Simple queues (bandwidth limits / quotas) endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.drivers import get_driver
from app.drivers.base import SimpleQueue as DriverSimpleQueue
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.queues import SimpleQueueCreate, SimpleQueuePublic
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services.device import _to_driver_creds, get_device

router = APIRouter()


@router.get("/{device_id}/queues/simple", response_model=list[SimpleQueuePublic])
async def list_simple_queues(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[SimpleQueuePublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).queue_simple_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        SimpleQueuePublic(
            id=q.id,
            name=q.name,
            target=q.target,
            max_limit=q.max_limit,
            burst_limit=q.burst_limit,
            burst_threshold=q.burst_threshold,
            burst_time=q.burst_time,
            parent=q.parent,
            priority=q.priority,
            bytes_in=q.bytes_in,
            bytes_out=q.bytes_out,
            disabled=q.disabled,
            comment=q.comment,
        )
        for q in items
    ]


@router.post(
    "/{device_id}/queues/simple",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_simple_queue(
    device_id: UUID,
    payload: SimpleQueueCreate,
    request: Request,
    user: User = Depends(require_permission("queue.simple", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    queue = DriverSimpleQueue(
        id=None,
        name=payload.name,
        target=payload.target,
        max_limit=payload.max_limit,
        burst_limit=payload.burst_limit,
        burst_threshold=payload.burst_threshold,
        burst_time=payload.burst_time,
        parent=payload.parent,
        priority=payload.priority,
        disabled=payload.disabled,
        comment=payload.comment,
    )
    try:
        new_id = await get_driver(device.vendor).queue_simple_add(
            _to_driver_creds(device), queue
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="queue.simple",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta={"queue_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.delete(
    "/{device_id}/queues/simple/{queue_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_simple_queue(
    device_id: UUID,
    queue_id: str,
    request: Request,
    user: User = Depends(require_permission("queue.simple", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).queue_simple_remove(
            _to_driver_creds(device), queue_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="queue.simple",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"queue_id": queue_id},
    )
    await session.commit()


@router.post(
    "/{device_id}/queues/simple/{queue_id}/reset-counters",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_simple_queue_counters(
    device_id: UUID,
    queue_id: str,
    request: Request,
    user: User = Depends(require_permission("queue.simple", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).queue_simple_reset_counters(
            _to_driver_creds(device), queue_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="queue.simple",
        action="reset_counters",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"queue_id": queue_id},
    )
    await session.commit()
