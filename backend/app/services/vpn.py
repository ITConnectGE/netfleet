"""VPN service — wraps vendor driver methods and emits secret-audit events.

Every code path that exposes plaintext secret material (passwords, keys)
MUST call `secret_audit.record_reveal()` before returning. Conversely,
every code path that changes a secret on the device must call
`secret_audit.record_rotation()` so the departing-user risk report can
deduce "still leaked" vs "rotated since".
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.drivers.base import (
    PppSecret as DriverPppSecret,
    WireguardInterface as DriverWgInterface,
    WireguardPeer as DriverWgPeer,
)
from app.models.secret_audit import SecretKind
from app.services import secret_audit as secret_audit_svc
from app.services.device import _to_driver_creds, get_device

log = structlog.get_logger(__name__)


class OperationError(Exception):
    """Wraps driver-side failures so endpoints can map them to 502."""


# ---------------- PPP secrets (L2TP / PPTP / SSTP / OVPN) ----------------


async def list_ppp_secrets(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> list[DriverPppSecret]:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).ppp_secrets_list(_to_driver_creds(device))
    except Exception as e:
        raise OperationError(str(e)) from e


async def add_ppp_secret(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    actor_user_id: UUID,
    *,
    name: str,
    service: str,
    password: str,
    profile: str | None,
    local_address: str | None,
    remote_address: str | None,
    comment: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> str:
    device = await get_device(session, organization_id, device_id)
    secret = DriverPppSecret(
        id=None,
        name=name,
        service=service,
        profile=profile,
        local_address=local_address,
        remote_address=remote_address,
        comment=comment,
    )
    try:
        new_id = await get_driver(device.vendor).ppp_secret_add(
            _to_driver_creds(device), secret, password
        )
    except Exception as e:
        raise OperationError(str(e)) from e

    # New secret means a brand-new credential exists — record as a rotation
    # so the risk report treats this as a fresh baseline (no past reveal applies).
    await secret_audit_svc.record_rotation(
        session,
        organization_id=organization_id,
        rotated_by_user_id=actor_user_id,
        device_id=device_id,
        secret_kind=SecretKind.PPP_PASSWORD,
        secret_identifier=new_id or name,
        note=f"created {service} secret '{name}'",
    )
    return new_id


async def set_ppp_secret_password(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    actor_user_id: UUID,
    *,
    secret_id: str,
    new_password: str,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).ppp_secret_set_password(
            _to_driver_creds(device), secret_id, new_password
        )
    except Exception as e:
        raise OperationError(str(e)) from e

    await secret_audit_svc.record_rotation(
        session,
        organization_id=organization_id,
        rotated_by_user_id=actor_user_id,
        device_id=device_id,
        secret_kind=SecretKind.PPP_PASSWORD,
        secret_identifier=secret_id,
        note="password reset",
    )


async def remove_ppp_secret(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    actor_user_id: UUID,
    *,
    secret_id: str,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).ppp_secret_remove(
            _to_driver_creds(device), secret_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e

    # Deleting the secret is conceptually the strongest possible rotation.
    await secret_audit_svc.record_rotation(
        session,
        organization_id=organization_id,
        rotated_by_user_id=actor_user_id,
        device_id=device_id,
        secret_kind=SecretKind.PPP_PASSWORD,
        secret_identifier=secret_id,
        note="secret deleted",
    )


async def reveal_ppp_secret_password(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    actor_user_id: UUID,
    *,
    secret_id: str,
    secret_label: str | None,
    justification: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> str:
    """Returns the plaintext password AND records a SecretReveal entry."""
    device = await get_device(session, organization_id, device_id)
    try:
        password = await get_driver(device.vendor).ppp_secret_reveal_password(
            _to_driver_creds(device), secret_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e

    await secret_audit_svc.record_reveal(
        session,
        organization_id=organization_id,
        user_id=actor_user_id,
        device_id=device_id,
        secret_kind=SecretKind.PPP_PASSWORD,
        secret_identifier=secret_id,
        secret_label=secret_label,
        ip_address=ip_address,
        user_agent=user_agent,
        justification=justification,
    )
    return password


# ---------------- WireGuard ----------------


async def list_wg_interfaces(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> list[DriverWgInterface]:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).wireguard_interfaces_list(
            _to_driver_creds(device)
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def add_wg_interface(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    name: str,
    listen_port: int | None,
    private_key: str | None,
    mtu: int | None,
    comment: str | None,
) -> str:
    device = await get_device(session, organization_id, device_id)
    iface = DriverWgInterface(
        id=None,
        name=name,
        listen_port=listen_port,
        private_key=private_key,
        mtu=mtu,
        comment=comment,
    )
    try:
        return await get_driver(device.vendor).wireguard_interface_add(
            _to_driver_creds(device), iface
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def remove_wg_interface(
    session: AsyncSession, organization_id: UUID, device_id: UUID, *, iface_id: str
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).wireguard_interface_remove(
            _to_driver_creds(device), iface_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def list_wg_peers(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    interface: str | None = None,
) -> list[DriverWgPeer]:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).wireguard_peers_list(
            _to_driver_creds(device), interface=interface
        )
    except Exception as e:
        raise OperationError(str(e)) from e


async def add_wg_peer(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    actor_user_id: UUID,
    *,
    interface: str,
    public_key: str,
    preshared_key: str | None,
    allowed_address: str | None,
    endpoint_address: str | None,
    endpoint_port: int | None,
    persistent_keepalive: int | None,
    comment: str | None,
) -> str:
    device = await get_device(session, organization_id, device_id)
    peer = DriverWgPeer(
        id=None,
        interface=interface,
        public_key=public_key,
        preshared_key=preshared_key,
        allowed_address=allowed_address,
        endpoint_address=endpoint_address,
        endpoint_port=endpoint_port,
        persistent_keepalive=persistent_keepalive,
        comment=comment,
    )
    try:
        new_id = await get_driver(device.vendor).wireguard_peer_add(
            _to_driver_creds(device), peer
        )
    except Exception as e:
        raise OperationError(str(e)) from e

    # New peer means fresh material — baseline rotation entry.
    await secret_audit_svc.record_rotation(
        session,
        organization_id=organization_id,
        rotated_by_user_id=actor_user_id,
        device_id=device_id,
        secret_kind=SecretKind.WIREGUARD_PRESHARED_KEY,
        secret_identifier=new_id or public_key,
        note=f"created WG peer on '{interface}'",
    )
    return new_id


async def remove_wg_peer(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    actor_user_id: UUID,
    *,
    peer_id: str,
) -> None:
    device = await get_device(session, organization_id, device_id)
    try:
        await get_driver(device.vendor).wireguard_peer_remove(
            _to_driver_creds(device), peer_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e

    await secret_audit_svc.record_rotation(
        session,
        organization_id=organization_id,
        rotated_by_user_id=actor_user_id,
        device_id=device_id,
        secret_kind=SecretKind.WIREGUARD_PRESHARED_KEY,
        secret_identifier=peer_id,
        note="WG peer deleted",
    )


async def reveal_wg_peer_keys(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    actor_user_id: UUID,
    *,
    peer_id: str,
    secret_label: str | None,
    justification: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> dict[str, str | None]:
    """Returns {public_key, preshared_key} for the peer and records a reveal."""
    device = await get_device(session, organization_id, device_id)
    try:
        keys = await get_driver(device.vendor).wireguard_peer_reveal_keys(
            _to_driver_creds(device), peer_id
        )
    except Exception as e:
        raise OperationError(str(e)) from e

    if keys.get("preshared_key"):
        await secret_audit_svc.record_reveal(
            session,
            organization_id=organization_id,
            user_id=actor_user_id,
            device_id=device_id,
            secret_kind=SecretKind.WIREGUARD_PRESHARED_KEY,
            secret_identifier=peer_id,
            secret_label=secret_label,
            ip_address=ip_address,
            user_agent=user_agent,
            justification=justification,
        )
    return keys
