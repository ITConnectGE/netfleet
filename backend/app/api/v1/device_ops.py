"""Per-device operations: IP services + device users."""

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
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.device_ops import (
    DeviceUserDisableRequest,
    DeviceUserPasswordReset,
    DeviceUserPublic,
    IpServicePublic,
    IpServiceUpdate,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services import device_ops as ops

router = APIRouter()


# ---------------- IP services ----------------


@router.get("/{device_id}/ip-services", response_model=list[IpServicePublic])
async def list_ip_services(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[IpServicePublic]:
    try:
        items = await ops.list_ip_services(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ops.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        IpServicePublic(
            name=s.name,
            port=s.port,
            enabled=s.enabled,
            address=s.address,
            certificate=s.certificate,
            tls_only=s.tls_only,
        )
        for s in items
    ]


@router.patch("/{device_id}/ip-services/{service_name}", status_code=status.HTTP_204_NO_CONTENT)
async def update_ip_service(
    device_id: UUID,
    service_name: str,
    payload: IpServiceUpdate,
    request: Request,
    user: User = Depends(require_permission("ip.service", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await ops.set_ip_service(
            session,
            user.organization_id,
            device_id,
            name=service_name,
            enabled=payload.enabled,
            port=payload.port,
            address=payload.address,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ops.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ip.service",
        action="update",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"service": service_name, **payload.model_dump(exclude_unset=True)},
    )
    await session.commit()


# ---------------- Device users ----------------


@router.get("/{device_id}/system-users", response_model=list[DeviceUserPublic])
async def list_device_users(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[DeviceUserPublic]:
    try:
        items = await ops.list_device_users(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ops.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        DeviceUserPublic(
            id=u.id,
            name=u.name,
            group=u.group,
            disabled=u.disabled,
            comment=u.comment,
            last_logged_in=u.last_logged_in,
        )
        for u in items
    ]


@router.post(
    "/{device_id}/system-users/{username}/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_device_user_password(
    device_id: UUID,
    username: str,
    payload: DeviceUserPasswordReset,
    request: Request,
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await ops.reset_device_user_password(
            session,
            user.organization_id,
            device_id,
            username=username,
            new_password=payload.new_password,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ops.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.user",
        action="reset_password",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"target_username": username},
    )
    await session.commit()


@router.post(
    "/{device_id}/system-users/{username}/disabled",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def set_device_user_disabled(
    device_id: UUID,
    username: str,
    payload: DeviceUserDisableRequest,
    request: Request,
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await ops.set_device_user_disabled(
            session,
            user.organization_id,
            device_id,
            username=username,
            disabled=payload.disabled,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ops.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.user",
        action="set_disabled",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"target_username": username, "disabled": payload.disabled},
    )
    await session.commit()
