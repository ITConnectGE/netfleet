"""DHCP endpoints — pools / servers / networks / leases."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, require_permission
from app.drivers import get_driver
from app.drivers.base import DhcpNetwork as DriverDhcpNetwork
from app.drivers.base import DhcpPool as DriverDhcpPool
from app.drivers.base import DhcpServer as DriverDhcpServer
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.dhcp import (
    DhcpLeaseCommentUpdate,
    DhcpLeasePublic,
    DhcpNetworkCreate,
    DhcpNetworkPublic,
    DhcpNetworkUpdate,
    DhcpPoolCreate,
    DhcpPoolPublic,
    DhcpPoolUpdate,
    DhcpServerCreate,
    DhcpServerPublic,
    DhcpServerUpdate,
)
from app.services import audit as audit_svc
from app.services.device import _to_driver_creds, get_device

router = APIRouter()


def _audit(
    *,
    action: str,
    section: str = "dhcp.server",
    device_id: UUID,
    payload: dict | None = None,
    response: dict | None = None,
):
    """Returns a closure shaped for write_audit; tiny shim so each
    endpoint stays linear-readable."""

    async def write(session, user: User, request: Request):
        await audit_svc.write_audit(
            session,
            user_id=user.id,
            organization_id=user.organization_id,
            section=section,
            action=action,
            outcome=AuditOutcome.OK,
            device_id=device_id,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_payload=payload,
            response_meta=response,
        )

    return write


# ---------------- Pools ----------------


@router.get(
    "/{device_id}/dhcp/pools",
    response_model=list[DhcpPoolPublic],
)
async def list_pools(
    device_id: UUID,
    user: User = Depends(require_permission("dhcp.server", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[DhcpPoolPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).dhcp_pools_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        DhcpPoolPublic(
            id=p.id,
            name=p.name,
            ranges=p.ranges,
            next_pool=p.next_pool,
            comment=p.comment,
        )
        for p in items
    ]


@router.post(
    "/{device_id}/dhcp/pools",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_pool(
    device_id: UUID,
    payload: DhcpPoolCreate,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    pool = DriverDhcpPool(
        id=None,
        name=payload.name,
        ranges=payload.ranges,
        next_pool=payload.next_pool,
        comment=payload.comment,
    )
    try:
        new_id = await get_driver(device.vendor).dhcp_pool_add(
            _to_driver_creds(device), pool
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="pool_create",
        device_id=device_id,
        payload=payload.model_dump(),
        response={"id": new_id},
    )(session, user, request)
    await session.commit()
    return {"id": new_id}


@router.patch(
    "/{device_id}/dhcp/pools/{pool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_pool(
    device_id: UUID,
    pool_id: str,
    payload: DhcpPoolUpdate,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    pool = DriverDhcpPool(
        id=pool_id,
        name=payload.name or "",
        ranges=payload.ranges or "",
        next_pool=payload.next_pool,
        comment=payload.comment,
    )
    try:
        await get_driver(device.vendor).dhcp_pool_update(
            _to_driver_creds(device), pool_id, pool
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="pool_update",
        device_id=device_id,
        payload={"pool_id": pool_id, **payload.model_dump(exclude_unset=True)},
    )(session, user, request)
    await session.commit()


@router.delete(
    "/{device_id}/dhcp/pools/{pool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_pool(
    device_id: UUID,
    pool_id: str,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).dhcp_pool_remove(
            _to_driver_creds(device), pool_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="pool_delete",
        device_id=device_id,
        payload={"pool_id": pool_id},
    )(session, user, request)
    await session.commit()


# ---------------- Servers ----------------


@router.get(
    "/{device_id}/dhcp/servers",
    response_model=list[DhcpServerPublic],
)
async def list_servers(
    device_id: UUID,
    user: User = Depends(require_permission("dhcp.server", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[DhcpServerPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).dhcp_servers_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        DhcpServerPublic(
            id=s.id,
            name=s.name,
            interface=s.interface,
            address_pool=s.address_pool,
            lease_time=s.lease_time,
            authoritative=s.authoritative,
            disabled=s.disabled,
            comment=s.comment,
        )
        for s in items
    ]


@router.post(
    "/{device_id}/dhcp/servers",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_server(
    device_id: UUID,
    payload: DhcpServerCreate,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    server = DriverDhcpServer(
        id=None,
        name=payload.name,
        interface=payload.interface,
        address_pool=payload.address_pool,
        lease_time=payload.lease_time,
        authoritative=payload.authoritative,
        disabled=payload.disabled,
        comment=payload.comment,
    )
    try:
        new_id = await get_driver(device.vendor).dhcp_server_add(
            _to_driver_creds(device), server
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="server_create",
        device_id=device_id,
        payload=payload.model_dump(),
        response={"id": new_id},
    )(session, user, request)
    await session.commit()
    return {"id": new_id}


@router.patch(
    "/{device_id}/dhcp/servers/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_server(
    device_id: UUID,
    server_id: str,
    payload: DhcpServerUpdate,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    server = DriverDhcpServer(
        id=server_id,
        name=payload.name or "",
        interface=payload.interface or "",
        address_pool=payload.address_pool,
        lease_time=payload.lease_time,
        authoritative=payload.authoritative,
        disabled=bool(payload.disabled) if payload.disabled is not None else False,
        comment=payload.comment,
    )
    try:
        await get_driver(device.vendor).dhcp_server_update(
            _to_driver_creds(device), server_id, server
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="server_update",
        device_id=device_id,
        payload={"server_id": server_id, **payload.model_dump(exclude_unset=True)},
    )(session, user, request)
    await session.commit()


@router.delete(
    "/{device_id}/dhcp/servers/{server_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_server(
    device_id: UUID,
    server_id: str,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).dhcp_server_remove(
            _to_driver_creds(device), server_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="server_delete",
        device_id=device_id,
        payload={"server_id": server_id},
    )(session, user, request)
    await session.commit()


# ---------------- Networks ----------------


@router.get(
    "/{device_id}/dhcp/networks",
    response_model=list[DhcpNetworkPublic],
)
async def list_networks(
    device_id: UUID,
    user: User = Depends(require_permission("dhcp.server", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[DhcpNetworkPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).dhcp_networks_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        DhcpNetworkPublic(
            id=n.id,
            address=n.address,
            gateway=n.gateway,
            netmask=n.netmask,
            dns_servers=n.dns_servers,
            ntp_servers=n.ntp_servers,
            domain=n.domain,
            comment=n.comment,
        )
        for n in items
    ]


@router.post(
    "/{device_id}/dhcp/networks",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_network(
    device_id: UUID,
    payload: DhcpNetworkCreate,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    network = DriverDhcpNetwork(
        id=None,
        address=payload.address,
        gateway=payload.gateway,
        netmask=payload.netmask,
        dns_servers=payload.dns_servers,
        ntp_servers=payload.ntp_servers,
        domain=payload.domain,
        comment=payload.comment,
    )
    try:
        new_id = await get_driver(device.vendor).dhcp_network_add(
            _to_driver_creds(device), network
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="network_create",
        device_id=device_id,
        payload=payload.model_dump(),
        response={"id": new_id},
    )(session, user, request)
    await session.commit()
    return {"id": new_id}


@router.patch(
    "/{device_id}/dhcp/networks/{network_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_network(
    device_id: UUID,
    network_id: str,
    payload: DhcpNetworkUpdate,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    network = DriverDhcpNetwork(
        id=network_id,
        address=payload.address or "",
        gateway=payload.gateway,
        netmask=payload.netmask,
        dns_servers=payload.dns_servers,
        ntp_servers=payload.ntp_servers,
        domain=payload.domain,
        comment=payload.comment,
    )
    try:
        await get_driver(device.vendor).dhcp_network_update(
            _to_driver_creds(device), network_id, network
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="network_update",
        device_id=device_id,
        payload={"network_id": network_id, **payload.model_dump(exclude_unset=True)},
    )(session, user, request)
    await session.commit()


@router.delete(
    "/{device_id}/dhcp/networks/{network_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_network(
    device_id: UUID,
    network_id: str,
    request: Request,
    user: User = Depends(require_permission("dhcp.server", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).dhcp_network_remove(
            _to_driver_creds(device), network_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="network_delete",
        device_id=device_id,
        payload={"network_id": network_id},
    )(session, user, request)
    await session.commit()


# ---------------- Leases ----------------


@router.get(
    "/{device_id}/dhcp/leases",
    response_model=list[DhcpLeasePublic],
)
async def list_leases(
    device_id: UUID,
    user: User = Depends(require_permission("dhcp.lease", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[DhcpLeasePublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).dhcp_leases(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        DhcpLeasePublic(
            id=lease.id,
            address=lease.address,
            mac_address=lease.mac_address,
            host_name=lease.host_name,
            client_id=lease.client_id,
            status=lease.status,
            server=lease.server,
            expires_at_iso=lease.expires_at_iso,
            dynamic=lease.dynamic,
            blocked=lease.blocked,
            comment=lease.comment,
        )
        for lease in items
    ]


@router.post(
    "/{device_id}/dhcp/leases/{lease_id}/make-static",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def lease_make_static(
    device_id: UUID,
    lease_id: str,
    request: Request,
    user: User = Depends(require_permission("dhcp.lease", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).dhcp_lease_make_static(
            _to_driver_creds(device), lease_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="lease_make_static",
        section="dhcp.lease",
        device_id=device_id,
        payload={"lease_id": lease_id},
    )(session, user, request)
    await session.commit()


@router.patch(
    "/{device_id}/dhcp/leases/{lease_id}/comment",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def lease_set_comment(
    device_id: UUID,
    lease_id: str,
    payload: DhcpLeaseCommentUpdate,
    request: Request,
    user: User = Depends(require_permission("dhcp.lease", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).dhcp_lease_set_comment(
            _to_driver_creds(device), lease_id, comment=payload.comment
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="lease_set_comment",
        section="dhcp.lease",
        device_id=device_id,
        payload={"lease_id": lease_id, "comment": payload.comment},
    )(session, user, request)
    await session.commit()


@router.delete(
    "/{device_id}/dhcp/leases/{lease_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def lease_remove(
    device_id: UUID,
    lease_id: str,
    request: Request,
    user: User = Depends(require_permission("dhcp.lease", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).dhcp_lease_remove(
            _to_driver_creds(device), lease_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    await _audit(
        action="lease_remove",
        section="dhcp.lease",
        device_id=device_id,
        payload={"lease_id": lease_id},
    )(session, user, request)
    await session.commit()
