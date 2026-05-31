"""Device service — CRUD with encrypted credentials + driver-mediated test connection."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field, encrypt_field
from app.drivers import get_driver
from app.drivers.base import DeviceCredentials as DriverCredentials
from app.models.device import Device, DeviceStatus
from app.models.site import Site
from app.schemas.device import DeviceCreate, DevicePublic, DeviceUpdate, TestConnectionResult

log = structlog.get_logger(__name__)


class DeviceNotFound(Exception):
    pass


class DeviceNameTaken(Exception):
    pass


class SiteNotInOrganization(Exception):
    pass


class UnknownVendor(Exception):
    pass


# ---------------- helpers ----------------


def to_public(d: Device) -> DevicePublic:
    return DevicePublic.model_validate(
        {
            **{
                k: getattr(d, k)
                for k in DevicePublic.model_fields
                if k not in {"has_password", "has_api_key"}
            },
            "has_password": d.password_encrypted is not None,
            "has_api_key": d.api_key_encrypted is not None,
        }
    )


def _to_driver_creds(d: Device) -> DriverCredentials:
    password = decrypt_field(d.password_encrypted) if d.password_encrypted else None
    api_key = decrypt_field(d.api_key_encrypted) if d.api_key_encrypted else None
    return DriverCredentials(
        host=d.host,
        port=d.port,
        username=d.username,
        password=password,
        api_key=api_key,
        transport=d.transport.value,
        verify_tls=d.verify_tls,
    )


async def _assert_site_in_org(session: AsyncSession, organization_id: UUID, site_id: UUID) -> None:
    stmt = select(Site.id).where(Site.id == site_id, Site.organization_id == organization_id)
    if (await session.execute(stmt)).first() is None:
        raise SiteNotInOrganization("site does not belong to this organization")


def _assert_known_vendor(vendor: str) -> None:
    try:
        get_driver(vendor)
    except ValueError as e:
        raise UnknownVendor(str(e)) from e


# ---------------- CRUD ----------------


async def list_devices(
    session: AsyncSession,
    organization_id: UUID,
    *,
    site_id: UUID | None = None,
) -> list[Device]:
    stmt = select(Device).where(Device.organization_id == organization_id)
    if site_id is not None:
        stmt = stmt.where(Device.site_id == site_id)
    stmt = stmt.order_by(Device.name)
    return list((await session.execute(stmt)).scalars())


async def get_device(session: AsyncSession, organization_id: UUID, device_id: UUID) -> Device:
    stmt = select(Device).where(Device.id == device_id, Device.organization_id == organization_id)
    device = (await session.execute(stmt)).scalar_one_or_none()
    if device is None:
        raise DeviceNotFound("device not found")
    return device


async def create_device(
    session: AsyncSession,
    organization_id: UUID,
    payload: DeviceCreate,
) -> Device:
    _assert_known_vendor(payload.vendor)
    await _assert_site_in_org(session, organization_id, payload.site_id)

    # uniqueness check
    dupe = (
        await session.execute(
            select(Device.id).where(
                Device.organization_id == organization_id, Device.name == payload.name
            )
        )
    ).first()
    if dupe is not None:
        raise DeviceNameTaken(f"device with name '{payload.name}' already exists")

    device = Device(
        organization_id=organization_id,
        site_id=payload.site_id,
        vendor=payload.vendor,
        name=payload.name,
        host=payload.host,
        port=payload.port,
        transport=payload.transport,
        verify_tls=payload.verify_tls,
        username=payload.username,
        password_encrypted=encrypt_field(payload.password) if payload.password else None,
        api_key_encrypted=encrypt_field(payload.api_key) if payload.api_key else None,
        notes=payload.notes,
        status=DeviceStatus.UNKNOWN,
    )
    session.add(device)
    await session.flush()
    return device


async def update_device(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    payload: DeviceUpdate,
) -> Device:
    device = await get_device(session, organization_id, device_id)
    data = payload.model_dump(exclude_unset=True)

    if "site_id" in data and data["site_id"] is not None:
        await _assert_site_in_org(session, organization_id, data["site_id"])

    if "password" in data:
        pw = data.pop("password")
        device.password_encrypted = encrypt_field(pw) if pw else None
    if "api_key" in data:
        k = data.pop("api_key")
        device.api_key_encrypted = encrypt_field(k) if k else None

    for k, v in data.items():
        setattr(device, k, v)

    await session.flush()
    return device


async def delete_device(session: AsyncSession, organization_id: UUID, device_id: UUID) -> None:
    device = await get_device(session, organization_id, device_id)
    await session.delete(device)
    await session.flush()


# ---------------- driver-mediated operations ----------------


async def test_connection(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
) -> TestConnectionResult:
    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    creds = _to_driver_creds(device)

    try:
        ok = await driver.test_connection(creds)
        if not ok:
            device.status = DeviceStatus.OFFLINE
            device.status_error = "test_connection returned False"
            await session.flush()
            return TestConnectionResult(ok=False, status="offline", error=device.status_error)

        info = await driver.system_info(creds)
        device.status = DeviceStatus.ONLINE
        device.status_error = None
        device.last_seen_at = datetime.now(UTC)
        # backfill discovered metadata
        if info.identity and not device.notes:
            pass  # identity != notes; leave notes alone
        device.model = info.model or device.model
        device.firmware = info.firmware or device.firmware
        device.serial = info.serial or device.serial
        await session.flush()
        return TestConnectionResult(
            ok=True,
            status="online",
            identity=info.identity,
            model=info.model,
            firmware=info.firmware,
            uptime_seconds=info.uptime_seconds,
        )
    except Exception as e:
        log.warning("device.test_connection.failed", device_id=str(device_id), error=str(e))
        device.status = DeviceStatus.ERROR
        device.status_error = str(e)[:1024]
        await session.flush()
        return TestConnectionResult(ok=False, status="error", error=str(e))
