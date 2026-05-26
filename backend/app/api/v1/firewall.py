"""Firewall filter + RouterOS log endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.drivers.base import FilterRule as DriverFilterRule
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.firewall import (
    FilterRuleCreate,
    FilterRulePublic,
    FilterRuleUpdate,
    LogEntryPublic,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services import firewall as fw_svc

router = APIRouter()


# ---------------- Filter ----------------


@router.get("/{device_id}/firewall/filter", response_model=list[FilterRulePublic])
async def list_filter(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[FilterRulePublic]:
    try:
        items = await fw_svc.list_filter(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        FilterRulePublic(
            id=r.id,
            chain=r.chain,
            action=r.action,
            src_address=r.src_address,
            dst_address=r.dst_address,
            src_address_list=r.src_address_list,
            dst_address_list=r.dst_address_list,
            protocol=r.protocol,
            src_port=r.src_port,
            dst_port=r.dst_port,
            in_interface=r.in_interface,
            out_interface=r.out_interface,
            connection_state=r.connection_state,
            log=r.log,
            log_prefix=r.log_prefix,
            disabled=r.disabled,
            comment=r.comment,
        )
        for r in items
    ]


@router.post(
    "/{device_id}/firewall/filter",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_filter(
    device_id: UUID,
    payload: FilterRuleCreate,
    request: Request,
    user: User = Depends(require_permission("firewall.filter", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    rule = DriverFilterRule(
        id=None,
        chain=payload.chain,
        action=payload.action,
        src_address=payload.src_address,
        dst_address=payload.dst_address,
        src_address_list=payload.src_address_list,
        dst_address_list=payload.dst_address_list,
        protocol=payload.protocol,
        src_port=payload.src_port,
        dst_port=payload.dst_port,
        in_interface=payload.in_interface,
        out_interface=payload.out_interface,
        connection_state=payload.connection_state,
        log=payload.log,
        log_prefix=payload.log_prefix,
        disabled=payload.disabled,
        comment=payload.comment,
    )
    try:
        new_id = await fw_svc.add_filter(session, user.organization_id, device_id, rule)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.filter",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta={"rule_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.patch(
    "/{device_id}/firewall/filter/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_filter(
    device_id: UUID,
    rule_id: str,
    payload: FilterRuleUpdate,
    request: Request,
    user: User = Depends(require_permission("firewall.filter", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await fw_svc.set_filter(
            session, user.organization_id, device_id, rule_id, disabled=payload.disabled
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.filter",
        action="update",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"rule_id": rule_id, **payload.model_dump(exclude_unset=True)},
    )
    await session.commit()


@router.delete(
    "/{device_id}/firewall/filter/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_filter(
    device_id: UUID,
    rule_id: str,
    request: Request,
    user: User = Depends(require_permission("firewall.filter", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await fw_svc.remove_filter(session, user.organization_id, device_id, rule_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.filter",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"rule_id": rule_id},
    )
    await session.commit()


# ---------------- Logs ----------------


@router.get("/{device_id}/logs", response_model=list[LogEntryPublic])
async def list_logs(
    device_id: UUID,
    topics: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=200, ge=1, le=2000),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[LogEntryPublic]:
    try:
        items = await fw_svc.list_logs(
            session, user.organization_id, device_id, topics=topics, limit=limit
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [LogEntryPublic(time=e.time, topics=e.topics, message=e.message) for e in items]
