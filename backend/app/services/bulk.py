"""Bulk operations across many devices in parallel."""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.drivers import get_driver
from app.drivers.base import DeviceCredentials, FilterRule
from app.models.device import Device
from app.schemas.device_ops import BulkOperationResult
from app.services.device import _to_driver_creds

log = structlog.get_logger(__name__)


async def bulk_password_reset(
    session: AsyncSession,
    organization_id: UUID,
    *,
    device_ids: list[UUID],
    username: str,
    new_password: str,
) -> list[BulkOperationResult]:
    """Reset `username` to `new_password` across each device in `device_ids`."""
    # Resolve & validate ownership upfront
    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id, Device.id.in_(device_ids)
                )
            )
        ).scalars()
    )
    found = {d.id: d for d in devices}

    semaphore = asyncio.Semaphore(settings.POLLER_CONCURRENCY)

    async def run_one(device_id: UUID) -> BulkOperationResult:
        d = found.get(device_id)
        if d is None:
            return BulkOperationResult(
                device_id=device_id,
                device_name=None,
                status="skipped",
                error="device not found in organization",
            )
        if not d.is_enabled:
            return BulkOperationResult(
                device_id=device_id, device_name=d.name, status="skipped", error="device disabled"
            )
        async with semaphore:
            try:
                driver = get_driver(d.vendor)
                creds: DeviceCredentials = _to_driver_creds(d)
                await driver.device_user_set_password(creds, username, new_password)
                return BulkOperationResult(device_id=device_id, device_name=d.name, status="ok")
            except Exception as e:
                log.warning("bulk.password_reset.failed", device_id=str(device_id), error=str(e))
                return BulkOperationResult(
                    device_id=device_id, device_name=d.name, status="failed", error=str(e)
                )

    return await asyncio.gather(*(run_one(did) for did in device_ids))


# ---------------- Address-list (P21 #13) ----------------


async def bulk_address_list_add(
    session: AsyncSession,
    organization_id: UUID,
    *,
    device_ids: list[UUID],
    list_name: str,
    address: str,
    comment: str | None,
    timeout: str | None,
) -> list[BulkOperationResult]:
    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id,
                    Device.id.in_(device_ids),
                )
            )
        ).scalars()
    )
    found = {d.id: d for d in devices}

    semaphore = asyncio.Semaphore(settings.POLLER_CONCURRENCY)

    async def run_one(device_id: UUID) -> BulkOperationResult:
        d = found.get(device_id)
        if d is None:
            return BulkOperationResult(
                device_id=device_id,
                device_name=None,
                status="skipped",
                error="device not found in organization",
            )
        if not d.is_enabled:
            return BulkOperationResult(
                device_id=device_id,
                device_name=d.name,
                status="skipped",
                error="device disabled",
            )
        async with semaphore:
            try:
                driver = get_driver(d.vendor)
                creds = _to_driver_creds(d)
                await driver.firewall_address_list_add(
                    creds,
                    list_name=list_name,
                    address=address,
                    comment=comment,
                    timeout=timeout,
                )
                return BulkOperationResult(
                    device_id=device_id, device_name=d.name, status="ok"
                )
            except Exception as e:
                log.warning(
                    "bulk.address_list_add.failed",
                    device_id=str(device_id),
                    error=str(e),
                )
                return BulkOperationResult(
                    device_id=device_id,
                    device_name=d.name,
                    status="failed",
                    error=str(e),
                )

    return await asyncio.gather(*(run_one(did) for did in device_ids))


# ---------------- Firewall filter (P21 #13) ----------------


async def bulk_firewall_filter_add(
    session: AsyncSession,
    organization_id: UUID,
    *,
    device_ids: list[UUID],
    rule: FilterRule,
) -> list[BulkOperationResult]:
    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id,
                    Device.id.in_(device_ids),
                )
            )
        ).scalars()
    )
    found = {d.id: d for d in devices}

    semaphore = asyncio.Semaphore(settings.POLLER_CONCURRENCY)

    async def run_one(device_id: UUID) -> BulkOperationResult:
        d = found.get(device_id)
        if d is None:
            return BulkOperationResult(
                device_id=device_id,
                device_name=None,
                status="skipped",
                error="device not found in organization",
            )
        if not d.is_enabled:
            return BulkOperationResult(
                device_id=device_id,
                device_name=d.name,
                status="skipped",
                error="device disabled",
            )
        async with semaphore:
            try:
                driver = get_driver(d.vendor)
                creds = _to_driver_creds(d)
                await driver.firewall_filter_add(creds, rule)
                return BulkOperationResult(
                    device_id=device_id, device_name=d.name, status="ok"
                )
            except Exception as e:
                log.warning(
                    "bulk.firewall_filter_add.failed",
                    device_id=str(device_id),
                    error=str(e),
                )
                return BulkOperationResult(
                    device_id=device_id,
                    device_name=d.name,
                    status="failed",
                    error=str(e),
                )

    return await asyncio.gather(*(run_one(did) for did in device_ids))
