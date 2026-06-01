"""Firewall filter + RouterOS log endpoints."""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.drivers.base import FilterRule as DriverFilterRule
from app.drivers.base import NatRule as DriverNatRule
from app.models.audit_log import AuditOutcome
from app.models.user import User
from pydantic import BaseModel

from app.schemas.firewall import (
    FilterRuleCreate,
    FilterRulePublic,
    FilterRuleUpdate,
    LogEntryPublic,
    NatRuleCreate,
    NatRulePublic,
    NatRuleUpdate,
)


class FilterRuleMoveRequest(BaseModel):
    """Reorder a filter rule. ``before_id`` is the .id of the rule the
    moved one should land in front of. Pass ``null`` (or omit) to move
    the rule to the bottom of the chain."""

    before_id: str | None = None
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

    out: list[FilterRulePublic] = []
    for r in items:
        try:
            out.append(
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
            )
        except Exception as e:
            # Surface bad RouterOS payloads as 502 with the offending row,
            # rather than letting the validator raise an opaque 500.
            log.warning(
                "firewall.filter.row_invalid",
                device_id=str(device_id),
                error=str(e),
                row=r.raw,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected firewall filter row from device: {e}",
            ) from e
    return out


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
            session,
            user.organization_id,
            device_id,
            rule_id,
            disabled=payload.disabled,
            log=payload.log,
            log_prefix=payload.log_prefix,
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


@router.post(
    "/{device_id}/firewall/filter/{rule_id}/reset-counters",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_filter_counters(
    device_id: UUID,
    rule_id: str,
    request: Request,
    user: User = Depends(require_permission("firewall.filter", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await fw_svc.reset_filter_counters(
            session, user.organization_id, device_id, rule_id
        )
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.filter",
        action="reset_counters",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"rule_id": rule_id},
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


@router.post(
    "/{device_id}/firewall/filter/{rule_id}/move",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def move_filter(
    device_id: UUID,
    rule_id: str,
    payload: FilterRuleMoveRequest,
    request: Request,
    user: User = Depends(require_permission("firewall.filter", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await fw_svc.move_filter(
            session,
            user.organization_id,
            device_id,
            rule_id,
            before_id=payload.before_id,
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
        action="move",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"rule_id": rule_id, "before_id": payload.before_id},
    )
    await session.commit()


# ---------------- NAT ----------------


@router.get("/{device_id}/firewall/nat", response_model=list[NatRulePublic])
async def list_nat(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[NatRulePublic]:
    try:
        items = await fw_svc.list_nat(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    out: list[NatRulePublic] = []
    for r in items:
        try:
            out.append(
                NatRulePublic(
                    id=r.id,
                    chain=r.chain,
                    action=r.action,
                    src_address=r.src_address,
                    dst_address=r.dst_address,
                    dst_port=r.dst_port,
                    protocol=r.protocol,
                    to_addresses=r.to_addresses,
                    to_ports=r.to_ports,
                    in_interface=r.in_interface,
                    out_interface=r.out_interface,
                    log=r.log,
                    log_prefix=r.log_prefix,
                    bytes_count=r.bytes_count,
                    packets_count=r.packets_count,
                    disabled=r.disabled,
                    comment=r.comment,
                )
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "firewall.nat.row_invalid",
                device_id=str(device_id),
                error=str(e),
                row=getattr(r, "raw", None),
            )
    return out


@router.post(
    "/{device_id}/firewall/nat",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_nat(
    device_id: UUID,
    payload: NatRuleCreate,
    request: Request,
    user: User = Depends(require_permission("firewall.nat", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    rule = DriverNatRule(
        id=None,
        chain=payload.chain,
        action=payload.action,
        src_address=payload.src_address,
        dst_address=payload.dst_address,
        dst_port=payload.dst_port,
        protocol=payload.protocol,
        to_addresses=payload.to_addresses,
        to_ports=payload.to_ports,
        in_interface=payload.in_interface,
        out_interface=payload.out_interface,
        log=payload.log,
        log_prefix=payload.log_prefix,
        disabled=payload.disabled,
        comment=payload.comment,
    )
    try:
        new_id = await fw_svc.add_nat(session, user.organization_id, device_id, rule)
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.nat",
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
    "/{device_id}/firewall/nat/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_nat(
    device_id: UUID,
    rule_id: str,
    payload: NatRuleUpdate,
    request: Request,
    user: User = Depends(require_permission("firewall.nat", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await fw_svc.set_nat(
            session,
            user.organization_id,
            device_id,
            rule_id,
            disabled=payload.disabled,
            log=payload.log,
            log_prefix=payload.log_prefix,
        )
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.nat",
        action="update",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"rule_id": rule_id, **payload.model_dump(exclude_unset=True)},
    )
    await session.commit()


@router.delete(
    "/{device_id}/firewall/nat/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_nat(
    device_id: UUID,
    rule_id: str,
    request: Request,
    user: User = Depends(require_permission("firewall.nat", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await fw_svc.remove_nat(session, user.organization_id, device_id, rule_id)
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.nat",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"rule_id": rule_id},
    )
    await session.commit()


@router.post(
    "/{device_id}/firewall/nat/{rule_id}/reset-counters",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_nat_counters(
    device_id: UUID,
    rule_id: str,
    request: Request,
    user: User = Depends(require_permission("firewall.nat", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await fw_svc.reset_nat_counters(
            session, user.organization_id, device_id, rule_id
        )
    except fw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.nat",
        action="reset_counters",
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
