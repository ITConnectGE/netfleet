"""Firmware service — check + persist per-device update availability."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.models.device import Device
from app.services.device import _to_driver_creds, get_device

log = structlog.get_logger(__name__)


class FirmwareError(Exception):
    pass


async def check_device_firmware(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> Device:
    device = await get_device(session, organization_id, device_id)
    try:
        info = await get_driver(device.vendor).firmware_check_updates(_to_driver_creds(device))
    except Exception as e:
        raise FirmwareError(str(e)) from e

    if info.current_version:
        device.firmware = info.current_version
    device.firmware_available = info.available_version
    device.firmware_channel = info.channel
    device.firmware_checked_at = datetime.now(UTC)
    device.routerboard_current = info.routerboard_current
    device.routerboard_available = info.routerboard_available
    await session.flush()
    return device


async def check_fleet_firmware(
    session: AsyncSession, organization_id: UUID
) -> tuple[int, int]:
    """Iterate every enabled device. Returns (checked_ok, failed)."""
    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id, Device.is_enabled.is_(True)
                )
            )
        ).scalars()
    )

    ok = 0
    failed = 0
    for d in devices:
        try:
            await check_device_firmware(session, organization_id, d.id)
            ok += 1
        except Exception as e:
            log.warning("firmware.check_failed", device_id=str(d.id), error=str(e))
            failed += 1
    return ok, failed


def needs_upgrade(device: Device) -> bool:
    """True iff RouterOS or routerboard reports a newer version available."""
    if (
        device.firmware_available
        and device.firmware
        and device.firmware_available != device.firmware
    ):
        return True
    if (
        device.routerboard_available
        and device.routerboard_current
        and device.routerboard_available != device.routerboard_current
    ):
        return True
    return False


async def fleet_summary(
    session: AsyncSession, organization_id: UUID
) -> dict[str, int]:
    """Counts of {total, updates_available, checked_ever, never_checked}."""
    total = int(
        (
            await session.execute(
                select(func.count(Device.id)).where(
                    Device.organization_id == organization_id, Device.is_enabled.is_(True)
                )
            )
        ).scalar_one()
    )
    rows = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id, Device.is_enabled.is_(True)
                )
            )
        ).scalars()
    )
    updates = sum(1 for d in rows if needs_upgrade(d))
    checked = sum(1 for d in rows if d.firmware_checked_at is not None)
    return {
        "total": total,
        "updates_available": updates,
        "checked_ever": checked,
        "never_checked": total - checked,
    }
