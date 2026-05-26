"""Single-device operations: IP services + device users.

Sits on top of the vendor driver. The API layer should call these (not the
driver directly) so RBAC and audit happen in one place.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.drivers.base import DeviceUser, IpService
from app.services.device import _to_driver_creds, get_device

log = structlog.get_logger(__name__)


class OperationError(Exception):
    """Raised when a device-side operation fails (e.g., user not found, RouterOS denies)."""


# ---------------- IP services ----------------


async def list_ip_services(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> list[IpService]:
    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    try:
        return await driver.ip_services_list(_to_driver_creds(device))
    except Exception as e:
        raise OperationError(str(e)) from e


async def set_ip_service(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    name: str,
    enabled: bool | None = None,
    port: int | None = None,
    address: str | None = None,
) -> None:
    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    try:
        await driver.ip_service_set(
            _to_driver_creds(device),
            name,
            enabled=enabled,
            port=port,
            address=address,
        )
    except Exception as e:
        raise OperationError(str(e)) from e


# ---------------- Device users ----------------


async def list_device_users(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> list[DeviceUser]:
    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    try:
        return await driver.device_users_list(_to_driver_creds(device))
    except Exception as e:
        raise OperationError(str(e)) from e


async def reset_device_user_password(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    username: str,
    new_password: str,
) -> None:
    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    try:
        await driver.device_user_set_password(
            _to_driver_creds(device), username, new_password
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def set_device_user_disabled(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    username: str,
    disabled: bool,
) -> None:
    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    try:
        await driver.device_user_set_disabled(
            _to_driver_creds(device), username, disabled
        )
    except Exception as e:
        raise OperationError(str(e)) from e
