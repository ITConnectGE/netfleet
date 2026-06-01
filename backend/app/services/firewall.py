"""Firewall + log service — driver-mediated."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.drivers.base import FilterRule as DriverFilterRule
from app.drivers.base import LogEntry as DriverLogEntry
from app.drivers.base import NatRule as DriverNatRule
from app.services.device import _to_driver_creds, get_device

log = structlog.get_logger(__name__)


class OperationError(Exception):
    pass


# ---------------- Filter ----------------


async def list_filter(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> list[DriverFilterRule]:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).firewall_filter_list(_to_driver_creds(device))
    except Exception as e:
        raise OperationError(str(e)) from e


async def add_filter(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    rule: DriverFilterRule,
) -> str:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).firewall_filter_add(
            _to_driver_creds(device), rule
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def set_filter(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    rule_id: str,
    *,
    disabled: bool | None = None,
    log: bool | None = None,
    log_prefix: str | None = None,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).firewall_filter_set(
            _to_driver_creds(device),
            rule_id,
            disabled=disabled,
            log=log,
            log_prefix=log_prefix,
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def reset_filter_counters(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    rule_id: str,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).firewall_filter_reset_counters(
            _to_driver_creds(device), rule_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e


# ---------------- NAT ----------------


async def list_nat(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> list[DriverNatRule]:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).firewall_nat_list(_to_driver_creds(device))
    except Exception as e:
        raise OperationError(str(e)) from e


async def add_nat(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    rule: DriverNatRule,
) -> str:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).firewall_nat_add(
            _to_driver_creds(device), rule
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def set_nat(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    rule_id: str,
    *,
    disabled: bool | None = None,
    log: bool | None = None,
    log_prefix: str | None = None,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).firewall_nat_set(
            _to_driver_creds(device),
            rule_id,
            disabled=disabled,
            log=log,
            log_prefix=log_prefix,
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def remove_nat(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    rule_id: str,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).firewall_nat_remove(
            _to_driver_creds(device), rule_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def reset_nat_counters(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    rule_id: str,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).firewall_nat_reset_counters(
            _to_driver_creds(device), rule_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def reset_interface_counters(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    interface_name: str,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).interface_reset_counters(
            _to_driver_creds(device), interface_name
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def remove_filter(
    session: AsyncSession, organization_id: UUID, device_id: UUID, rule_id: str
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).firewall_filter_remove(
            _to_driver_creds(device), rule_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def move_filter(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    rule_id: str,
    *,
    before_id: str | None,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).firewall_filter_move(
            _to_driver_creds(device), rule_id, before_id=before_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e


# ---------------- Logs ----------------


async def list_logs(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    topics: str | None = None,
    limit: int = 200,
) -> list[DriverLogEntry]:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).log_list(
            _to_driver_creds(device), topics=topics, limit=limit
        )
    except Exception as e:
        raise OperationError(str(e)) from e
