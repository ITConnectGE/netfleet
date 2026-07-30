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
from app.models.device import Device, DeviceClass, DeviceStatus, DeviceTransport
from app.models.site import Site
from app.schemas.device import (
    SERVER_VENDORS,
    DeviceCreate,
    DevicePublic,
    DeviceUpdate,
    TestConnectionResult,
    assert_posix_username,
)
from app.services.ssh_keys import generate_ed25519_keypair

log = structlog.get_logger(__name__)


class DeviceNotFound(Exception):
    pass


class DeviceNameTaken(Exception):
    pass


class SiteNotInOrganization(Exception):
    pass


class UnknownVendor(Exception):
    pass


class InvalidDeviceField(Exception):
    """A field failed a rule the schema could not check on its own —
    currently only the server account-name rule, which needs the device's
    vendor and so cannot live on `DeviceUpdate`."""


class HostKeyNotPinned(Exception):
    """An SSH device is being used before its host key has been pinned.

    Pinning happens on the first successful "Test connection". Until then
    the transport would accept *any* host key — which is the inherent TOFU
    window, except that nothing else on the read paths ever records the
    fingerprint, so for a device that is never explicitly tested the window
    would stay open forever. Failing closed turns a silent MITM opportunity
    into one visible action the operator has to take."""


# ---------------- helpers ----------------


_DERIVED_PUBLIC_FIELDS = {"has_password", "has_api_key", "has_ssh_key"}


def to_public(d: Device) -> DevicePublic:
    return DevicePublic.model_validate(
        {
            **{
                k: getattr(d, k)
                for k in DevicePublic.model_fields
                if k not in _DERIVED_PUBLIC_FIELDS
            },
            "has_password": d.password_encrypted is not None,
            "has_api_key": d.api_key_encrypted is not None,
            "has_ssh_key": d.ssh_private_key_encrypted is not None,
        }
    )


def _to_driver_creds(d: Device, *, allow_first_connect: bool = False) -> DriverCredentials:
    """Build driver credentials for `d`.

    `allow_first_connect` is the one escape hatch from the host-key pin
    requirement, and only `test_connection` sets it — that is the call
    whose whole job is to establish the pin.
    """
    if (
        d.transport is DeviceTransport.SSH
        and d.ssh_host_key_fingerprint is None
        and not allow_first_connect
    ):
        raise HostKeyNotPinned(
            f"the SSH host key for '{d.name}' has not been verified yet — "
            "run Test connection on this device first"
        )

    password = decrypt_field(d.password_encrypted) if d.password_encrypted else None
    api_key = decrypt_field(d.api_key_encrypted) if d.api_key_encrypted else None
    ssh_key = (
        decrypt_field(d.ssh_private_key_encrypted) if d.ssh_private_key_encrypted else None
    )
    ssh_passphrase = (
        decrypt_field(d.ssh_key_passphrase_encrypted)
        if d.ssh_key_passphrase_encrypted
        else None
    )
    become_password = (
        decrypt_field(d.become_password_encrypted) if d.become_password_encrypted else None
    )
    return DriverCredentials(
        host=d.host,
        port=d.port,
        username=d.username,
        password=password,
        api_key=api_key,
        transport=d.transport.value,
        verify_tls=d.verify_tls,
        ssh_port=d.ssh_port or 22,
        ssh_private_key=ssh_key,
        ssh_key_passphrase=ssh_passphrase,
        become_method=d.become_method.value,
        become_password=become_password,
        host_key_fingerprint=d.ssh_host_key_fingerprint,
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

    ssh_private_key = payload.ssh_private_key
    if payload.generate_ssh_key:
        # A fixed comment, not the device name. Only the private half is
        # stored, and its comment is never read: the onboarding script
        # re-derives the public key with a UUID-based comment. Deriving it
        # from the name here bought nothing and rejected every display name
        # containing a space.
        ssh_private_key = generate_ed25519_keypair(comment="netfleet").private_pem

    device = Device(
        organization_id=organization_id,
        site_id=payload.site_id,
        vendor=payload.vendor,
        device_class=(
            DeviceClass.SERVER if payload.vendor in SERVER_VENDORS else DeviceClass.NETWORK
        ),
        name=payload.name,
        host=payload.host,
        port=payload.port,
        ssh_port=payload.ssh_port,
        transport=payload.transport,
        verify_tls=payload.verify_tls,
        username=payload.username,
        password_encrypted=encrypt_field(payload.password) if payload.password else None,
        api_key_encrypted=encrypt_field(payload.api_key) if payload.api_key else None,
        ssh_private_key_encrypted=(
            encrypt_field(ssh_private_key) if ssh_private_key else None
        ),
        become_method=payload.become_method,
        become_password_encrypted=(
            encrypt_field(payload.become_password) if payload.become_password else None
        ),
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

    # DeviceUpdate has no vendor field, so the server-only account-name rule
    # can only be enforced here, where the device is in hand. Re-raised as a
    # typed error: a bare ValueError out of a service becomes a 500.
    if device.vendor in SERVER_VENDORS and data.get("username"):
        try:
            assert_posix_username(data["username"])
        except ValueError as e:
            raise InvalidDeviceField(str(e)) from e

    if "password" in data:
        pw = data.pop("password")
        device.password_encrypted = encrypt_field(pw) if pw else None
    if "api_key" in data:
        k = data.pop("api_key")
        device.api_key_encrypted = encrypt_field(k) if k else None
    if "ssh_private_key" in data:
        key = data.pop("ssh_private_key")
        device.ssh_private_key_encrypted = encrypt_field(key) if key else None
    if "become_password" in data:
        bp = data.pop("become_password")
        device.become_password_encrypted = encrypt_field(bp) if bp else None
    # Re-pin on the next connection. Only meaningful after a legitimate
    # rebuild — an unexplained host-key change is what the pin is for.
    if data.pop("reset_host_key", False):
        device.ssh_host_key_fingerprint = None
    # NOT NULL column — an explicit null in the payload means "leave it".
    if data.get("become_method") is None:
        data.pop("become_method", None)

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
    creds = _to_driver_creds(device, allow_first_connect=True)

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
        device.os_family = info.os_family or device.os_family
        device.os_version = info.os_version or device.os_version
        # Trust on first use: SSH drivers report the host key they saw. A
        # mismatch never reaches here — the driver raises instead — so this
        # only ever writes the first-connect value.
        if device.ssh_host_key_fingerprint is None:
            fingerprint = info.raw.get("host_key_fingerprint")
            if fingerprint:
                device.ssh_host_key_fingerprint = str(fingerprint)[:128]
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
