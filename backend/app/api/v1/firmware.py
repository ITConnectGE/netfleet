"""Firmware-check + upgrade endpoints."""

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
from app.schemas.firmware import (
    AutoUpgradePolicyPublic,
    AutoUpgradePolicyUpdate,
    FirmwareStatusPublic,
    FirmwareUpgradeRequest,
    FirmwareUpgradeResult,
    FirmwareUpgradeStatus,
    FleetFirmwareSummary,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services import firmware as fw_svc

router = APIRouter()


@router.get("/firmware/summary", response_model=FleetFirmwareSummary)
async def fleet_firmware_summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> FleetFirmwareSummary:
    s = await fw_svc.fleet_summary(session, user.organization_id)
    return FleetFirmwareSummary(**s)


@router.get(
    "/devices/{device_id}/firmware", response_model=FirmwareStatusPublic
)
async def get_device_firmware(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> FirmwareStatusPublic:
    try:
        device = await device_svc.get_device(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return FirmwareStatusPublic(
        current_version=device.firmware,
        available_version=device.firmware_available,
        channel=device.firmware_channel,
        checked_at=device.firmware_checked_at,
        routerboard_current=device.routerboard_current,
        routerboard_available=device.routerboard_available,
        needs_upgrade=fw_svc.needs_upgrade(device),
    )


@router.post(
    "/devices/{device_id}/firmware/check",
    response_model=FirmwareStatusPublic,
)
async def trigger_firmware_check(
    device_id: UUID,
    request: Request,
    user: User = Depends(require_permission("system.info", "read")),
    session: AsyncSession = Depends(db_session),
) -> FirmwareStatusPublic:
    try:
        device = await fw_svc.check_device_firmware(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except fw_svc.FirmwareError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.firmware",
        action="check",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        response_meta={
            "current": device.firmware,
            "available": device.firmware_available,
            "channel": device.firmware_channel,
        },
    )
    await session.commit()
    return FirmwareStatusPublic(
        current_version=device.firmware,
        available_version=device.firmware_available,
        channel=device.firmware_channel,
        checked_at=device.firmware_checked_at,
        routerboard_current=device.routerboard_current,
        routerboard_available=device.routerboard_available,
        needs_upgrade=fw_svc.needs_upgrade(device),
    )


# ============== Upgrade ==============


@router.post(
    "/devices/{device_id}/firmware/upgrade",
    response_model=FirmwareUpgradeResult,
)
async def trigger_firmware_upgrade(
    device_id: UUID,
    payload: FirmwareUpgradeRequest,
    request: Request,
    user: User = Depends(require_permission("system.firmware", "execute")),
    session: AsyncSession = Depends(db_session),
) -> FirmwareUpgradeResult:
    try:
        device = await fw_svc.trigger_firmware_upgrade(
            session,
            user.organization_id,
            device_id,
            include_routerboard=payload.include_routerboard,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except fw_svc.FirmwareError as e:
        await audit_svc.write_audit(
            session,
            user_id=user.id,
            organization_id=user.organization_id,
            section="system.firmware",
            action="upgrade",
            outcome=AuditOutcome.FAILED,
            device_id=device_id,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            error_message=str(e),
        )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.firmware",
        action="upgrade",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"include_routerboard": payload.include_routerboard},
        response_meta={
            "from": device.last_upgrade_from_version,
            "to": device.last_upgrade_to_version,
        },
    )
    await session.commit()
    return FirmwareUpgradeResult(
        triggered=True,
        will_reboot=True,
        from_version=device.last_upgrade_from_version,
        to_version=device.last_upgrade_to_version,
        message="Upgrade initiated — device will reboot. Re-check firmware after it comes back.",
    )


@router.get(
    "/devices/{device_id}/firmware/upgrade-status",
    response_model=FirmwareUpgradeStatus,
)
async def get_upgrade_status(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> FirmwareUpgradeStatus:
    try:
        device = await device_svc.get_device(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return FirmwareUpgradeStatus(
        last_triggered_at=device.last_upgrade_triggered_at,
        last_status=device.last_upgrade_status,
        last_error=device.last_upgrade_error,
        last_from_version=device.last_upgrade_from_version,
        last_to_version=device.last_upgrade_to_version,
    )


# ============== Auto-upgrade policy ==============


@router.get(
    "/devices/{device_id}/firmware/policy",
    response_model=AutoUpgradePolicyPublic,
)
async def get_auto_upgrade_policy(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AutoUpgradePolicyPublic:
    try:
        device = await device_svc.get_device(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return AutoUpgradePolicyPublic(
        enabled=device.auto_upgrade_enabled,
        window_start_hour=device.auto_upgrade_window_start_hour,
        window_end_hour=device.auto_upgrade_window_end_hour,
    )


@router.put(
    "/devices/{device_id}/firmware/policy",
    response_model=AutoUpgradePolicyPublic,
)
async def set_auto_upgrade_policy(
    device_id: UUID,
    payload: AutoUpgradePolicyUpdate,
    request: Request,
    user: User = Depends(require_permission("system.firmware", "execute")),
    session: AsyncSession = Depends(db_session),
) -> AutoUpgradePolicyPublic:
    try:
        device = await fw_svc.set_auto_upgrade_policy(
            session,
            user.organization_id,
            device_id,
            enabled=payload.enabled,
            window_start_hour=payload.window_start_hour,
            window_end_hour=payload.window_end_hour,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.firmware",
        action="set_policy",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
    )
    await session.commit()
    return AutoUpgradePolicyPublic(
        enabled=device.auto_upgrade_enabled,
        window_start_hour=device.auto_upgrade_window_start_hour,
        window_end_hour=device.auto_upgrade_window_end_hour,
    )
