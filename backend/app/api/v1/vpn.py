"""VPN endpoints — PPP secrets (L2TP/PPTP/SSTP/OVPN) + WireGuard."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.drivers import get_driver
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.secret_audit import RevealRequest
from app.schemas.vpn import (
    PppSecretCreate,
    PppSecretPasswordReset,
    PppSecretPublic,
    WireguardInterfaceCreate,
    WireguardInterfacePublic,
    WireguardPeerConfigRequest,
    WireguardPeerCreate,
    WireguardPeerPublic,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services import vpn as vpn_svc
from app.services import wireguard as wg
from app.services.device import _to_driver_creds

router = APIRouter()


class WgEndpointSuggestion(BaseModel):
    """One row in /devices/{id}/wireguard/-/endpoints-suggested."""

    address: str
    interface: str
    comment: str | None = None


class WgSubnetSuggestion(BaseModel):
    """One row in /devices/{id}/wireguard/-/lan-subnets-suggested.

    ``cidr`` is the subnet in slash-notation (e.g. 10.0.0.0/24) — that's
    what the operator pastes into AllowedIPs."""

    cidr: str
    interface: str
    comment: str | None = None


# ---------------- PPP secrets ----------------


@router.get("/{device_id}/ppp-secrets", response_model=list[PppSecretPublic])
async def list_ppp_secrets(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[PppSecretPublic]:
    try:
        items = await vpn_svc.list_ppp_secrets(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        PppSecretPublic(
            id=s.id,
            name=s.name,
            service=s.service,
            profile=s.profile,
            local_address=s.local_address,
            remote_address=s.remote_address,
            disabled=s.disabled,
            comment=s.comment,
        )
        for s in items
    ]


@router.post(
    "/{device_id}/ppp-secrets",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_ppp_secret(
    device_id: UUID,
    payload: PppSecretCreate,
    request: Request,
    user: User = Depends(require_permission("ppp.secret", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    try:
        new_id = await vpn_svc.add_ppp_secret(
            session,
            user.organization_id,
            device_id,
            user.id,
            name=payload.name,
            service=payload.service,
            password=payload.password,
            profile=payload.profile,
            local_address=payload.local_address,
            remote_address=payload.remote_address,
            comment=payload.comment,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ppp.secret",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude={"password"}),
        response_meta={"secret_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.post(
    "/{device_id}/ppp-secrets/{secret_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_ppp_secret_password(
    device_id: UUID,
    secret_id: str,
    payload: PppSecretPasswordReset,
    request: Request,
    user: User = Depends(require_permission("ppp.secret", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await vpn_svc.set_ppp_secret_password(
            session,
            user.organization_id,
            device_id,
            user.id,
            secret_id=secret_id,
            new_password=payload.new_password,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ppp.secret",
        action="reset_password",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"secret_id": secret_id},
    )
    await session.commit()


@router.delete(
    "/{device_id}/ppp-secrets/{secret_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_ppp_secret(
    device_id: UUID,
    secret_id: str,
    request: Request,
    user: User = Depends(require_permission("ppp.secret", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await vpn_svc.remove_ppp_secret(
            session,
            user.organization_id,
            device_id,
            user.id,
            secret_id=secret_id,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ppp.secret",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"secret_id": secret_id},
    )
    await session.commit()


@router.post(
    "/{device_id}/ppp-secrets/{secret_id}/reveal",
    response_model=dict,
)
async def reveal_ppp_secret(
    device_id: UUID,
    secret_id: str,
    payload: RevealRequest,
    request: Request,
    user: User = Depends(require_permission("secret.reveal", "execute")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """Returns the plaintext password and records the reveal in the audit trail."""
    try:
        # Fetch the secret label for the audit row (best-effort).
        secrets = await vpn_svc.list_ppp_secrets(session, user.organization_id, device_id)
        label = next((f"{s.name} ({s.service})" for s in secrets if s.id == secret_id), None)

        password = await vpn_svc.reveal_ppp_secret_password(
            session,
            user.organization_id,
            device_id,
            user.id,
            secret_id=secret_id,
            secret_label=label,
            justification=payload.justification,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="secret.reveal",
        action="ppp_secret",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"secret_id": secret_id, "justification": payload.justification},
    )
    await session.commit()
    return {"password": password}


# ---------------- WireGuard interfaces ----------------


@router.get(
    "/{device_id}/wireguard/interfaces", response_model=list[WireguardInterfacePublic]
)
async def list_wg_interfaces(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[WireguardInterfacePublic]:
    try:
        items = await vpn_svc.list_wg_interfaces(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        WireguardInterfacePublic(
            id=i.id,
            name=i.name,
            listen_port=i.listen_port,
            public_key=i.public_key,
            mtu=i.mtu,
            disabled=i.disabled,
            comment=i.comment,
        )
        for i in items
    ]


@router.post(
    "/{device_id}/wireguard/interfaces",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_wg_interface(
    device_id: UUID,
    payload: WireguardInterfaceCreate,
    request: Request,
    user: User = Depends(require_permission("vpn.wireguard.interface", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    # If user didn't bring a private key, generate one server-side.
    private_key = payload.private_key
    generated = False
    if not private_key:
        kp = wg.generate_keypair()
        private_key = kp.private_b64
        generated = True

    try:
        new_id = await vpn_svc.add_wg_interface(
            session,
            user.organization_id,
            device_id,
            name=payload.name,
            listen_port=payload.listen_port,
            private_key=private_key,
            mtu=payload.mtu,
            comment=payload.comment,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="vpn.wireguard.interface",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "name": payload.name,
            "listen_port": payload.listen_port,
            "key_source": "generated" if generated else "user-provided",
        },
        response_meta={"interface_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.delete(
    "/{device_id}/wireguard/interfaces/{iface_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_wg_interface(
    device_id: UUID,
    iface_id: str,
    request: Request,
    user: User = Depends(require_permission("vpn.wireguard.interface", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await vpn_svc.remove_wg_interface(
            session, user.organization_id, device_id, iface_id=iface_id
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="vpn.wireguard.interface",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"interface_id": iface_id},
    )
    await session.commit()


# ---------------- WireGuard peers ----------------


@router.get("/{device_id}/wireguard/peers", response_model=list[WireguardPeerPublic])
async def list_wg_peers(
    device_id: UUID,
    interface: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[WireguardPeerPublic]:
    try:
        items = await vpn_svc.list_wg_peers(
            session, user.organization_id, device_id, interface=interface
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        WireguardPeerPublic(
            id=p.id,
            interface=p.interface,
            public_key=p.public_key,
            allowed_address=p.allowed_address,
            endpoint_address=p.endpoint_address,
            endpoint_port=p.endpoint_port,
            persistent_keepalive=p.persistent_keepalive,
            disabled=p.disabled,
            comment=p.comment,
        )
        for p in items
    ]


@router.post(
    "/{device_id}/wireguard/peers",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_wg_peer(
    device_id: UUID,
    payload: WireguardPeerCreate,
    request: Request,
    user: User = Depends(require_permission("vpn.wireguard.peer", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    # Optionally generate a PSK if not provided
    psk = payload.preshared_key
    psk_generated = False
    if psk is None:
        psk = wg.generate_preshared_key()
        psk_generated = True

    try:
        new_id = await vpn_svc.add_wg_peer(
            session,
            user.organization_id,
            device_id,
            user.id,
            interface=payload.interface,
            public_key=payload.public_key,
            preshared_key=psk,
            allowed_address=payload.allowed_address,
            endpoint_address=payload.endpoint_address,
            endpoint_port=payload.endpoint_port,
            persistent_keepalive=payload.persistent_keepalive,
            comment=payload.comment,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="vpn.wireguard.peer",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "interface": payload.interface,
            "allowed_address": payload.allowed_address,
            "psk_source": "generated" if psk_generated else "user-provided",
        },
        response_meta={"peer_id": new_id},
    )
    await session.commit()
    # Return the (possibly generated) PSK so the admin can save it once.
    return {"id": new_id, "preshared_key": psk}


@router.delete(
    "/{device_id}/wireguard/peers/{peer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_wg_peer(
    device_id: UUID,
    peer_id: str,
    request: Request,
    user: User = Depends(require_permission("vpn.wireguard.peer", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await vpn_svc.remove_wg_peer(
            session, user.organization_id, device_id, user.id, peer_id=peer_id
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="vpn.wireguard.peer",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"peer_id": peer_id},
    )
    await session.commit()


@router.post(
    "/{device_id}/wireguard/peers/{peer_id}/reveal",
    response_model=dict,
)
async def reveal_wg_peer_keys(
    device_id: UUID,
    peer_id: str,
    payload: RevealRequest,
    request: Request,
    user: User = Depends(require_permission("secret.reveal", "execute")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    try:
        peers = await vpn_svc.list_wg_peers(session, user.organization_id, device_id)
        label = next(
            (f"WG peer on {p.interface} ({p.public_key[:10]}…)" for p in peers if p.id == peer_id),
            None,
        )
        keys = await vpn_svc.reveal_wg_peer_keys(
            session,
            user.organization_id,
            device_id,
            user.id,
            peer_id=peer_id,
            secret_label=label,
            justification=payload.justification,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="secret.reveal",
        action="wireguard_peer_keys",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"peer_id": peer_id, "justification": payload.justification},
    )
    await session.commit()
    return keys


@router.post(
    "/{device_id}/wireguard/peers/{peer_id}/config",
    response_class=PlainTextResponse,
)
async def generate_wg_client_config(
    device_id: UUID,
    peer_id: str,
    payload: WireguardPeerConfigRequest,
    request: Request,
    user: User = Depends(require_permission("vpn.wireguard.peer", "read")),
    session: AsyncSession = Depends(db_session),
):
    """Assemble a wg-quick client config from the peer + caller-supplied params.

    The client's private key is generated server-side and shown ONCE in this
    response (the audit log records that this user saw it). The server-stored
    PSK is included if present.
    """
    try:
        peers = await vpn_svc.list_wg_peers(session, user.organization_id, device_id)
        peer = next((p for p in peers if p.id == peer_id), None)
        if peer is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="peer not found")

        # Find the parent interface's public key.
        interfaces = await vpn_svc.list_wg_interfaces(session, user.organization_id, device_id)
        iface = next((i for i in interfaces if i.name == peer.interface), None)
        if iface is None or not iface.public_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"interface '{peer.interface}' has no public key on the device",
            )

        # PSK is server-stored; reveal it (audited).
        keys = await vpn_svc.reveal_wg_peer_keys(
            session,
            user.organization_id,
            device_id,
            user.id,
            peer_id=peer_id,
            secret_label=f"WG peer config download ({peer.interface})",
            justification="generate client .conf",
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    # Server-side client key generation: the private key is shown once to admin.
    client_kp = wg.generate_keypair()

    conf = wg.build_client_config(
        client_private_key=client_kp.private_b64,
        client_address=payload.client_address,
        client_dns=payload.client_dns,
        server_public_key=iface.public_key,
        preshared_key=keys.get("preshared_key"),
        endpoint_host=payload.server_endpoint,
        endpoint_port=payload.server_endpoint_port,
        allowed_ips=payload.allowed_ips,
        persistent_keepalive=payload.persistent_keepalive,
    )

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="vpn.wireguard.peer",
        action="generate_client_config",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta={"peer_id": peer_id, "client_pubkey": client_kp.public_b64},
    )
    await session.commit()

    filename = f"netfleet-{peer.interface}-{peer_id}.conf"
    return PlainTextResponse(
        conf,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="text/plain",
    )


@router.get(
    "/{device_id}/wireguard/-/endpoints-suggested",
    response_model=list[WgEndpointSuggestion],
)
async def list_wg_endpoint_suggestions(
    device_id: UUID,
    user: User = Depends(require_permission("vpn.wireguard.peer", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[WgEndpointSuggestion]:
    """Return the device's WAN IPs so the operator can pick one as the
    client config Endpoint without typing it. We treat any interface
    listed in /interface/list list=WAN as a public-facing interface;
    the operator can still type a different value (CGNAT-bypass DDNS,
    floating IP, etc.) in the UI."""
    device = await get_device_for_actor(session, user, device_id)
    driver = get_driver(device.vendor)
    creds = _to_driver_creds(device)
    try:
        wan_ifaces = set(
            (await driver.interface_list_members(creds, "WAN")) or []
        )
        addresses = await driver.ip_addresses_list(creds)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    out: list[WgEndpointSuggestion] = []
    for a in addresses:
        if not a.interface or a.disabled or a.invalid:
            continue
        if wan_ifaces and a.interface not in wan_ifaces:
            continue
        # Strip "/24" etc. — the endpoint takes a bare host.
        host = (a.address or "").split("/", 1)[0]
        if not host:
            continue
        out.append(
            WgEndpointSuggestion(
                address=host, interface=a.interface, comment=a.comment
            )
        )
    return out


@router.get(
    "/{device_id}/wireguard/-/lan-subnets-suggested",
    response_model=list[WgSubnetSuggestion],
)
async def list_wg_lan_subnets(
    device_id: UUID,
    user: User = Depends(require_permission("vpn.wireguard.peer", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[WgSubnetSuggestion]:
    """Return the device's known IPv4 subnets so the AllowedIPs picker
    can show "tick the LANs this peer needs to reach". Interfaces that
    appear in /interface/list list=WAN are excluded — peer AllowedIPs
    aimed at WANs are usually accidental."""
    device = await get_device_for_actor(session, user, device_id)
    driver = get_driver(device.vendor)
    creds = _to_driver_creds(device)
    try:
        wan_ifaces = set(
            (await driver.interface_list_members(creds, "WAN")) or []
        )
        addresses = await driver.ip_addresses_list(creds)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    seen: set[str] = set()
    out: list[WgSubnetSuggestion] = []
    for a in addresses:
        if not a.interface or a.disabled or a.invalid:
            continue
        if a.interface in wan_ifaces:
            continue
        # We want the subnet, not the host bit. RouterOS exposes
        # ``address`` like "10.0.0.1/24" and ``network`` as "10.0.0.0".
        addr = (a.address or "").strip()
        if "/" not in addr:
            continue
        host, prefix = addr.split("/", 1)
        cidr = (
            f"{a.network}/{prefix}"
            if a.network
            else f"{host}/{prefix}"
        )
        if cidr in seen:
            continue
        seen.add(cidr)
        out.append(
            WgSubnetSuggestion(
                cidr=cidr, interface=a.interface, comment=a.comment
            )
        )
    return out


async def get_device_for_actor(
    session: AsyncSession, actor: User, device_id: UUID
):
    """Tiny convenience: pull the device row + 404 if not in this org."""
    try:
        return await device_svc.get_device(session, actor.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
