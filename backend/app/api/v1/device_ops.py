"""Per-device operations: IP services + device users."""

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
from app.drivers import get_driver
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.device_ops import (
    DeviceGroupCreate,
    DeviceGroupPublic,
    DeviceUserCreate,
    DeviceUserDisableRequest,
    DeviceUserGroupsUpdate,
    DeviceUserPasswordReset,
    DeviceUserPublic,
    IpServicePublic,
    IpServiceUpdate,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services import device_ops as ops
from app.services.device import _to_driver_creds, get_device

router = APIRouter()


# ---------------- Reboot ----------------


@router.post(
    "/{device_id}/reboot",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reboot_device(
    device_id: UUID,
    request: Request,
    user: User = Depends(require_permission("system.reboot", "execute")),
    session: AsyncSession = Depends(db_session),
) -> None:
    """Trigger a clean reboot on the device. The router drops the API
    session as part of the operation, so a 204 from this endpoint just
    means "the reboot was enqueued" — confirmation will come from the
    next Test Connection cycle a couple of minutes later."""
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).system_reboot(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.reboot",
        action="trigger",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()


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
            uid=u.uid,
            gid=u.gid,
            groups=u.groups,
            shell=u.shell,
            home=u.home,
            is_system=u.is_system,
            is_protected=u.is_protected,
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


# ---------------- Host accounts: create / delete / groups ----------------


async def _audit_user_op(
    session: AsyncSession,
    *,
    user: User,
    request: Request,
    device_id: UUID,
    action: str,
    payload: dict,
) -> None:
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.user",
        action=action,
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload,
    )
    await session.commit()


def _to_http(e: Exception) -> HTTPException:
    if isinstance(e, device_svc.DeviceNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.post("/{device_id}/system-users", status_code=status.HTTP_204_NO_CONTENT)
async def create_device_user(
    device_id: UUID,
    payload: DeviceUserCreate,
    request: Request,
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await ops.create_device_user(
            session,
            user.organization_id,
            device_id,
            username=payload.username,
            password=payload.password,
            groups=payload.groups,
            shell=payload.shell,
            comment=payload.comment,
            create_home=payload.create_home,
        )
    except (device_svc.DeviceNotFound, ops.OperationError) as e:
        raise _to_http(e) from e

    # The password is excluded by name here and would also be caught by the
    # audit redactor — both, because this one costs nothing.
    await _audit_user_op(
        session,
        user=user,
        request=request,
        device_id=device_id,
        action="create",
        payload=payload.model_dump(exclude={"password"}),
    )


@router.delete(
    "/{device_id}/system-users/{username}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_device_user(
    device_id: UUID,
    username: str,
    request: Request,
    remove_home: bool = Query(default=False),
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await ops.delete_device_user(
            session, user.organization_id, device_id, username, remove_home=remove_home
        )
    except (device_svc.DeviceNotFound, ops.OperationError) as e:
        raise _to_http(e) from e

    await _audit_user_op(
        session,
        user=user,
        request=request,
        device_id=device_id,
        action="delete",
        payload={"target_username": username, "remove_home": remove_home},
    )


@router.put(
    "/{device_id}/system-users/{username}/groups",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def set_device_user_groups(
    device_id: UUID,
    username: str,
    payload: DeviceUserGroupsUpdate,
    request: Request,
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await ops.set_device_user_groups(
            session, user.organization_id, device_id, username, payload.groups
        )
    except (device_svc.DeviceNotFound, ops.OperationError) as e:
        raise _to_http(e) from e

    await _audit_user_op(
        session,
        user=user,
        request=request,
        device_id=device_id,
        action="set_groups",
        payload={"target_username": username, "groups": payload.groups},
    )


@router.get("/{device_id}/system-groups", response_model=list[DeviceGroupPublic])
async def list_device_groups(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[DeviceGroupPublic]:
    try:
        groups = await ops.list_device_groups(session, user.organization_id, device_id)
    except (device_svc.DeviceNotFound, ops.OperationError) as e:
        raise _to_http(e) from e
    return [
        DeviceGroupPublic(
            name=g.name, gid=g.gid, members=g.members, is_system=g.is_system
        )
        for g in groups
    ]


@router.post("/{device_id}/system-groups", status_code=status.HTTP_204_NO_CONTENT)
async def create_device_group(
    device_id: UUID,
    payload: DeviceGroupCreate,
    request: Request,
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await ops.create_device_group(
            session, user.organization_id, device_id, payload.name
        )
    except (device_svc.DeviceNotFound, ops.OperationError) as e:
        raise _to_http(e) from e

    await _audit_user_op(
        session,
        user=user,
        request=request,
        device_id=device_id,
        action="create_group",
        payload={"name": payload.name},
    )


@router.delete(
    "/{device_id}/system-groups/{name}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_device_group(
    device_id: UUID,
    name: str,
    request: Request,
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await ops.delete_device_group(session, user.organization_id, device_id, name)
    except (device_svc.DeviceNotFound, ops.OperationError) as e:
        raise _to_http(e) from e

    await _audit_user_op(
        session,
        user=user,
        request=request,
        device_id=device_id,
        action="delete_group",
        payload={"name": name},
    )
