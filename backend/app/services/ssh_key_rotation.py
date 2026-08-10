"""Rotating the key NetFleet manages a Linux host with.

The order below is the entire safety of this operation, and it is the reverse
of the obvious one. The new key is installed *alongside* the old, proven on a
connection that uses only the new key, and only then does the old one go. At
every point before that final step the host is still reachable with the key
NetFleet already has, so a rotation that fails leaves the device exactly as it
was rather than unmanageable.

Nothing here is guarded by `change_guard`: there is nothing to roll back. A
failed step is undone by removing the line we added, over a connection we know
still works.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field, encrypt_field
from app.drivers import get_driver
from app.models.device import Device, DeviceClass
from app.services.device import _to_driver_creds, get_device
from app.services.ssh_keys import (
    fingerprint_from_public_openssh,
    generate_ed25519_keypair,
    key_blob,
    public_key_from_private_pem,
)

log = structlog.get_logger(__name__)


class RotationError(Exception):
    pass


class RotationFailedButSafe(RotationError):
    """The new key did not work. The old one still does, and the device is
    unchanged — which is the only outcome worth having when this goes wrong."""


async def rotate_management_key(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
) -> str:
    """Replace this device's management key. Returns the new fingerprint."""
    device: Device = await get_device(session, organization_id, device_id)
    if device.device_class is not DeviceClass.SERVER:
        raise RotationError("only Linux hosts have a NetFleet-managed SSH key")

    driver = get_driver(device.vendor)
    creds = _to_driver_creds(device)

    # Keyed on the device UUID, never on the display name. This string is
    # appended to a public key and that whole line is written into a remote
    # authorized_keys; a name-derived comment would let anyone who can rename
    # a device append a second key of their choosing.
    comment = f"netfleet-{device.id}"
    old_pem = (
        decrypt_field(device.ssh_private_key_encrypted)
        if device.ssh_private_key_encrypted
        else None
    )
    old_blob = (
        key_blob(public_key_from_private_pem(old_pem, comment=comment))
        if old_pem
        else None
    )

    new_pair = generate_ed25519_keypair(comment="netfleet")
    new_public = public_key_from_private_pem(new_pair.private_pem, comment=comment)
    new_blob = key_blob(new_public)

    # 1. Install the new key beside the old one.
    await driver.authorized_key_add(
        creds, username=device.username, public_key=new_public
    )

    # 2. Prove it on a connection that can only succeed with the new key.
    #    The password is cleared as well as the old key: a device configured
    #    with both would otherwise fall back and report a working rotation
    #    when the key itself was never accepted.
    probe = replace(creds, ssh_private_key=new_pair.private_pem, password=None)
    try:
        working = await driver.test_connection(probe)
    except Exception as e:  # noqa: BLE001 - any failure means "do not proceed"
        working = False
        log.info("ssh_key_rotation.probe_failed", device_id=str(device_id), error=str(e))

    if not working:
        # 3. Undo, over the connection we know still works.
        try:
            await driver.authorized_key_remove(
                creds, username=device.username, blob=new_blob
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "ssh_key_rotation.cleanup_failed",
                device_id=str(device_id),
                error=str(e)[:200],
            )
            raise RotationError(
                "The new key did not work and NetFleet could not remove it "
                "again. The old key still works, but the host now has an "
                f"unused NetFleet key in {device.username}'s authorized_keys "
                "that should be cleaned up by hand."
            ) from e
        raise RotationFailedButSafe(
            "The new key was installed but the host would not accept it, so it "
            "was removed again. Nothing changed — the existing key still works. "
            f"Check the permissions on {device.username}'s ~/.ssh (0700) and "
            "authorized_keys (0600): sshd ignores them silently when they are "
            "too open."
        )

    # 4. Only now is the new key the one NetFleet holds.
    device.ssh_private_key_encrypted = encrypt_field(new_pair.private_pem)
    await session.commit()

    # 5. Retire the old one, over the new connection — the proven one.
    if old_blob and old_blob != new_blob:
        try:
            await driver.authorized_key_remove(
                probe, username=device.username, blob=old_blob
            )
        except Exception as e:  # noqa: BLE001 - the rotation itself succeeded
            log.warning(
                "ssh_key_rotation.old_key_not_removed",
                device_id=str(device_id),
                error=str(e)[:200],
            )

    return fingerprint_from_public_openssh(new_public)
