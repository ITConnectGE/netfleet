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
    await reconcile_upgrade_outcome(device)
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


async def trigger_firmware_upgrade(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    include_routerboard: bool = False,
) -> Device:
    """Kick off the device's pending RouterOS upgrade. The device reboots.

    We mark `last_upgrade_status='pending'` *before* the driver call. If the
    driver raises (auth refused, no update, etc.), we flip to 'failed' with
    the error. A successful trigger leaves the row at 'pending' because the
    actual install runs on the device — the next firmware-check after reboot
    will reveal whether `firmware == last_upgrade_to_version`, at which point
    the next caller (or the auto-upgrade job) flips it to 'succeeded'.
    """
    device = await get_device(session, organization_id, device_id)

    from_v = device.firmware
    to_v = device.firmware_available

    device.last_upgrade_triggered_at = datetime.now(UTC)
    device.last_upgrade_status = "pending"
    device.last_upgrade_error = None
    device.last_upgrade_from_version = from_v
    device.last_upgrade_to_version = to_v
    await session.flush()

    driver = get_driver(device.vendor)
    creds = _to_driver_creds(device)
    try:
        await driver.firmware_upgrade(creds)
        if include_routerboard and device.routerboard_available and (
            device.routerboard_available != device.routerboard_current
        ):
            # Best-effort — RouterOS upgrade reboots first, so this often
            # won't run synchronously. Caller can re-trigger after the box
            # comes back if needed.
            try:
                await driver.firmware_routerboard_upgrade(creds)
            except Exception as e:
                log.warning(
                    "firmware.routerboard_upgrade_failed",
                    device_id=str(device.id),
                    error=str(e),
                )
    except Exception as e:
        device.last_upgrade_status = "failed"
        device.last_upgrade_error = str(e)[:2000]
        await session.flush()
        raise FirmwareError(str(e)) from e

    return device


async def reconcile_upgrade_outcome(device: Device) -> None:
    """Inspect a device after a firmware-check and flip pending→succeeded
    when the installed version matches the upgrade target."""
    if device.last_upgrade_status != "pending":
        return
    if device.last_upgrade_to_version and device.firmware == device.last_upgrade_to_version:
        device.last_upgrade_status = "succeeded"
        device.last_upgrade_error = None


async def set_auto_upgrade_policy(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    enabled: bool,
    window_start_hour: int | None,
    window_end_hour: int | None,
) -> Device:
    device = await get_device(session, organization_id, device_id)
    device.auto_upgrade_enabled = enabled
    device.auto_upgrade_window_start_hour = window_start_hour
    device.auto_upgrade_window_end_hour = window_end_hour
    await session.flush()
    return device


def _hour_in_window(hour: int, start: int | None, end: int | None) -> bool:
    """Inclusive-start, exclusive-end window. Wraps midnight when start>end.
    `None` window means always-eligible (the toggle alone gates auto-upgrade)."""
    if start is None or end is None:
        return True
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


async def auto_upgrade_run(
    session: AsyncSession, organization_id: UUID, *, now_hour: int | None = None
) -> tuple[int, int, int]:
    """Walk every enabled device with auto_upgrade_enabled=True whose window
    contains the current UTC hour, and trigger an upgrade if needs_upgrade.

    Returns (eligible, upgraded, failed).
    """
    if now_hour is None:
        now_hour = datetime.now(UTC).hour

    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id,
                    Device.is_enabled.is_(True),
                    Device.auto_upgrade_enabled.is_(True),
                )
            )
        ).scalars()
    )

    eligible = 0
    upgraded = 0
    failed = 0
    for d in devices:
        if not _hour_in_window(
            now_hour, d.auto_upgrade_window_start_hour, d.auto_upgrade_window_end_hour
        ):
            continue
        if not needs_upgrade(d):
            continue
        # Don't re-trigger if a previous attempt is still pending (device may
        # still be rebooting / installing).
        if d.last_upgrade_status == "pending":
            continue
        eligible += 1
        try:
            await trigger_firmware_upgrade(session, organization_id, d.id)
            upgraded += 1
        except Exception as e:
            log.warning(
                "firmware.auto_upgrade_failed",
                device_id=str(d.id),
                error=str(e),
            )
            failed += 1
    return eligible, upgraded, failed


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
