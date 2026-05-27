"""IP routes / addresses / ARP / Bridge hosts / Interfaces / VLANs endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.drivers import get_driver
from app.drivers.base import IpRoute as DriverIpRoute
from app.drivers.base import VlanInterface as DriverVlan
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.network import (
    ArpPublic,
    BridgeHostPublic,
    InterfacePublic,
    IpAddressPublic,
    IpRouteCreate,
    IpRoutePublic,
    NeighborPublic,
    VlanCreate,
    VlanPublic,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services.device import _to_driver_creds, get_device

router = APIRouter()


def _gateway(coro):
    """Translate any unexpected driver exception into 502."""

    async def runner():
        try:
            return await coro
        except device_svc.DeviceNotFound as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    return runner()


# ---------------- Routes ----------------


@router.get("/{device_id}/routes", response_model=list[IpRoutePublic])
async def list_routes(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[IpRoutePublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).ip_routes_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        IpRoutePublic(
            id=r.id,
            dst_address=r.dst_address,
            gateway=r.gateway,
            distance=r.distance,
            routing_table=r.routing_table,
            pref_src=r.pref_src,
            active=r.active,
            dynamic=r.dynamic,
            static=r.static,
            disabled=r.disabled,
            comment=r.comment,
        )
        for r in items
    ]


@router.post(
    "/{device_id}/routes",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_route(
    device_id: UUID,
    payload: IpRouteCreate,
    request: Request,
    user: User = Depends(require_permission("ip.route", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    route = DriverIpRoute(
        id=None,
        dst_address=payload.dst_address,
        gateway=payload.gateway,
        distance=payload.distance,
        routing_table=payload.routing_table,
        pref_src=payload.pref_src,
        disabled=payload.disabled,
        comment=payload.comment,
    )
    try:
        new_id = await get_driver(device.vendor).ip_route_add(_to_driver_creds(device), route)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ip.route",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta={"route_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.delete(
    "/{device_id}/routes/{route_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_route(
    device_id: UUID,
    route_id: str,
    request: Request,
    user: User = Depends(require_permission("ip.route", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).ip_route_remove(_to_driver_creds(device), route_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ip.route",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"route_id": route_id},
    )
    await session.commit()


# ---------------- Addresses ----------------


@router.get("/{device_id}/addresses", response_model=list[IpAddressPublic])
async def list_addresses(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[IpAddressPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).ip_addresses_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        IpAddressPublic(
            id=a.id,
            address=a.address,
            network=a.network,
            interface=a.interface,
            disabled=a.disabled,
            invalid=a.invalid,
            comment=a.comment,
        )
        for a in items
    ]


# ---------------- ARP ----------------


@router.get("/{device_id}/arp", response_model=list[ArpPublic])
async def list_arp(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[ArpPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).ip_arp_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        ArpPublic(
            id=a.id,
            address=a.address,
            mac_address=a.mac_address,
            interface=a.interface,
            complete=a.complete,
            dynamic=a.dynamic,
            invalid=a.invalid,
            comment=a.comment,
        )
        for a in items
    ]


# ---------------- Bridge hosts ----------------


@router.get("/{device_id}/bridge-hosts", response_model=list[BridgeHostPublic])
async def list_bridge_hosts(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[BridgeHostPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).bridge_hosts_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        BridgeHostPublic(
            id=h.id,
            mac_address=h.mac_address,
            on_interface=h.on_interface,
            bridge=h.bridge,
            age=h.age,
            dynamic=h.dynamic,
            external=h.external,
        )
        for h in items
    ]


# ---------------- Neighbours (CDP / LLDP / MNDP) ----------------


@router.get("/{device_id}/neighbors", response_model=list[NeighborPublic])
async def list_neighbors(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[NeighborPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).ip_neighbors_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        NeighborPublic(
            id=n.id,
            interface=n.interface,
            address=n.address,
            address6=n.address6,
            mac_address=n.mac_address,
            identity=n.identity,
            platform=n.platform,
            version=n.version,
            board=n.board,
            interface_name=n.interface_name,
            discovered_by=n.discovered_by,
            age=n.age,
            uptime=n.uptime,
        )
        for n in items
    ]


# ---------------- Interfaces ----------------


@router.get("/{device_id}/interfaces", response_model=list[InterfacePublic])
async def list_interfaces(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[InterfacePublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).interfaces_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        InterfacePublic(
            id=i.id,
            name=i.name,
            type=i.type,
            running=i.running,
            disabled=i.disabled,
            mac_address=i.mac_address,
            mtu=i.mtu,
            actual_mtu=i.actual_mtu,
            rx_bytes=i.rx_bytes,
            tx_bytes=i.tx_bytes,
            comment=i.comment,
        )
        for i in items
    ]


# ---------------- VLANs ----------------


@router.get("/{device_id}/vlans", response_model=list[VlanPublic])
async def list_vlans(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[VlanPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).vlan_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        VlanPublic(
            id=v.id,
            name=v.name,
            interface=v.interface,
            vlan_id=v.vlan_id,
            mtu=v.mtu,
            disabled=v.disabled,
            comment=v.comment,
        )
        for v in items
    ]


@router.post(
    "/{device_id}/vlans", response_model=dict, status_code=status.HTTP_201_CREATED
)
async def create_vlan(
    device_id: UUID,
    payload: VlanCreate,
    request: Request,
    user: User = Depends(require_permission("interface.list", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    vlan = DriverVlan(
        id=None,
        name=payload.name,
        interface=payload.interface,
        vlan_id=payload.vlan_id,
        mtu=payload.mtu,
        comment=payload.comment,
    )
    try:
        new_id = await get_driver(device.vendor).vlan_add(_to_driver_creds(device), vlan)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="interface.vlan",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta={"vlan_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.delete(
    "/{device_id}/vlans/{vlan_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_vlan(
    device_id: UUID,
    vlan_id: str,
    request: Request,
    user: User = Depends(require_permission("interface.list", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).vlan_remove(_to_driver_creds(device), vlan_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="interface.vlan",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"vlan_id": vlan_id},
    )
    await session.commit()
