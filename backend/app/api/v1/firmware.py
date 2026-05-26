"""Firmware-check endpoints (Phase 7b) — upgrades land in Phase 8."""

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
from app.schemas.firmware import FirmwareStatusPublic, FleetFirmwareSummary
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
