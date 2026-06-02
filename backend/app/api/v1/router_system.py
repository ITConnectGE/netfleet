"""Router-side system configuration endpoints (NTP, SNMP)."""

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
from app.drivers.base import SnmpCommunity as DriverSnmpCommunity
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.router_system import (
    DeviceClockPublic,
    DeviceClockUpdate,
    LoggingActionCreate,
    LoggingActionPublic,
    LoggingRuleCreate,
    LoggingRulePublic,
    LoggingRuleUpdate,
    NtpClientPublic,
    NtpClientUpdate,
    NtpServerPublic,
    NtpServerUpdate,
    SnmpCommunityCreate,
    SnmpCommunityPublic,
    SnmpCommunityUpdate,
    SnmpPublic,
    SnmpUpdate,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services.device import _to_driver_creds, get_device

router = APIRouter()


def _wrap_driver(coro):
    """Translate driver exceptions into 502."""

    async def runner():
        try:
            return await coro
        except device_svc.DeviceNotFound as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    return runner()


# ---------------- NTP client ----------------


@router.get("/{device_id}/ntp", response_model=NtpClientPublic)
async def get_ntp(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> NtpClientPublic:
    device = await get_device(session, user.organization_id, device_id)
    try:
        ntp = await get_driver(device.vendor).ntp_client_get(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return NtpClientPublic(
        enabled=ntp.enabled,
        mode=ntp.mode,
        servers=ntp.servers,
        primary=ntp.primary,
        secondary=ntp.secondary,
    )


@router.patch("/{device_id}/ntp", status_code=status.HTTP_204_NO_CONTENT)
async def update_ntp(
    device_id: UUID,
    payload: NtpClientUpdate,
    request: Request,
    user: User = Depends(require_permission("system.info", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).ntp_client_set(
            _to_driver_creds(device),
            enabled=payload.enabled,
            mode=payload.mode,
            servers=payload.servers,
            primary=payload.primary,
            secondary=payload.secondary,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.ntp",
        action="update",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()


# ---------------- NTP server (router serving time) ----------------


@router.get("/{device_id}/ntp-server", response_model=NtpServerPublic)
async def get_ntp_server(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> NtpServerPublic:
    device = await get_device(session, user.organization_id, device_id)
    try:
        s = await get_driver(device.vendor).ntp_server_get(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return NtpServerPublic(
        enabled=s.enabled,
        broadcast=s.broadcast,
        multicast=s.multicast,
        manycast=s.manycast,
        auth_key=s.auth_key,
    )


@router.patch("/{device_id}/ntp-server", status_code=status.HTTP_204_NO_CONTENT)
async def update_ntp_server(
    device_id: UUID,
    payload: NtpServerUpdate,
    request: Request,
    user: User = Depends(require_permission("system.info", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).ntp_server_set(
            _to_driver_creds(device),
            enabled=payload.enabled,
            broadcast=payload.broadcast,
            multicast=payload.multicast,
            manycast=payload.manycast,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.ntp",
        action="update_server",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()


# ---------------- Device clock ----------------


@router.get("/{device_id}/clock", response_model=DeviceClockPublic)
async def get_device_clock(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> DeviceClockPublic:
    device = await get_device(session, user.organization_id, device_id)
    try:
        c = await get_driver(device.vendor).clock_get(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return DeviceClockPublic(
        time=c.time,
        date=c.date,
        time_zone_name=c.time_zone_name,
        time_zone_autodetect=c.time_zone_autodetect,
        gmt_offset=c.gmt_offset,
        dst_active=c.dst_active,
    )


@router.patch("/{device_id}/clock", status_code=status.HTTP_204_NO_CONTENT)
async def update_device_clock(
    device_id: UUID,
    payload: DeviceClockUpdate,
    request: Request,
    user: User = Depends(require_permission("system.info", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).clock_set(
            _to_driver_creds(device),
            time_zone_name=payload.time_zone_name,
            time_zone_autodetect=payload.time_zone_autodetect,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.clock",
        action="update",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()


# ---------------- SNMP ----------------


@router.get("/{device_id}/snmp", response_model=SnmpPublic)
async def get_snmp(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> SnmpPublic:
    device = await get_device(session, user.organization_id, device_id)
    try:
        snmp = await get_driver(device.vendor).snmp_get(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return SnmpPublic(
        enabled=snmp.enabled,
        contact=snmp.contact,
        location=snmp.location,
        trap_target=snmp.trap_target,
        trap_version=snmp.trap_version,
        engine_id=snmp.engine_id,
    )


@router.patch("/{device_id}/snmp", status_code=status.HTTP_204_NO_CONTENT)
async def update_snmp(
    device_id: UUID,
    payload: SnmpUpdate,
    request: Request,
    user: User = Depends(require_permission("system.info", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).snmp_set(
            _to_driver_creds(device),
            enabled=payload.enabled,
            contact=payload.contact,
            location=payload.location,
            trap_target=payload.trap_target,
            trap_version=payload.trap_version,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.snmp",
        action="update",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()


@router.get(
    "/{device_id}/snmp/communities", response_model=list[SnmpCommunityPublic]
)
async def list_snmp_communities(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[SnmpCommunityPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).snmp_community_list(_to_driver_creds(device))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        SnmpCommunityPublic(
            id=c.id,
            name=c.name,
            addresses=c.addresses,
            security=c.security,
            read_access=c.read_access,
            write_access=c.write_access,
            disabled=c.disabled,
        )
        for c in items
    ]


@router.post(
    "/{device_id}/snmp/communities",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_snmp_community(
    device_id: UUID,
    payload: SnmpCommunityCreate,
    request: Request,
    user: User = Depends(require_permission("system.info", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    community = DriverSnmpCommunity(
        id=None,
        name=payload.name,
        addresses=payload.addresses,
        security=payload.security,
        read_access=payload.read_access,
        write_access=payload.write_access,
    )
    try:
        new_id = await get_driver(device.vendor).snmp_community_add(
            _to_driver_creds(device), community
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.snmp",
        action="create_community",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta={"community_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.patch(
    "/{device_id}/snmp/communities/{community_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_snmp_community(
    device_id: UUID,
    community_id: str,
    payload: SnmpCommunityUpdate,
    request: Request,
    user: User = Depends(require_permission("system.info", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).snmp_community_update(
            _to_driver_creds(device),
            community_id,
            name=payload.name,
            addresses=payload.addresses,
            security=payload.security,
            read_access=payload.read_access,
            write_access=payload.write_access,
            disabled=payload.disabled,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.snmp",
        action="update_community",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "community_id": community_id,
            **payload.model_dump(exclude_unset=True),
        },
    )
    await session.commit()


@router.delete(
    "/{device_id}/snmp/communities/{community_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_snmp_community(
    device_id: UUID,
    community_id: str,
    request: Request,
    user: User = Depends(require_permission("system.info", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).snmp_community_remove(
            _to_driver_creds(device), community_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.snmp",
        action="delete_community",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"community_id": community_id},
    )
    await session.commit()


# ---------------- /system/logging — rules ----------------


def _rule_to_public(r) -> LoggingRulePublic:
    return LoggingRulePublic(
        id=r.id,
        topics=r.topics,
        action=r.action,
        prefix=r.prefix,
        disabled=r.disabled,
        invalid=r.invalid,
        default=r.default,
    )


@router.get(
    "/{device_id}/logging/rules",
    response_model=list[LoggingRulePublic],
)
async def list_logging_rules(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[LoggingRulePublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).system_logging_list(
            _to_driver_creds(device)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e
    return [_rule_to_public(r) for r in items]


@router.post(
    "/{device_id}/logging/rules",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_logging_rule(
    device_id: UUID,
    payload: LoggingRuleCreate,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    try:
        new_id = await get_driver(device.vendor).system_logging_add(
            _to_driver_creds(device),
            topics=payload.topics,
            action=payload.action,
            prefix=payload.prefix,
            disabled=payload.disabled,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="create_logging_rule",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta={"rule_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.patch(
    "/{device_id}/logging/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_logging_rule(
    device_id: UUID,
    rule_id: str,
    payload: LoggingRuleUpdate,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).system_logging_set(
            _to_driver_creds(device),
            rule_id,
            topics=payload.topics,
            action=payload.action,
            prefix=payload.prefix,
            disabled=payload.disabled,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="update_logging_rule",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"rule_id": rule_id, **payload.model_dump(exclude_unset=True)},
    )
    await session.commit()


@router.delete(
    "/{device_id}/logging/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_logging_rule(
    device_id: UUID,
    rule_id: str,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).system_logging_remove(
            _to_driver_creds(device), rule_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="delete_logging_rule",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"rule_id": rule_id},
    )
    await session.commit()


# ---------------- /system/logging — actions ----------------


def _action_to_public(a) -> LoggingActionPublic:
    return LoggingActionPublic(
        id=a.id,
        name=a.name,
        target=a.target,
        remote=a.remote,
        remote_port=a.remote_port,
        src_address=a.src_address,
        bsd_syslog=a.bsd_syslog,
        syslog_facility=a.syslog_facility,
        syslog_severity=a.syslog_severity,
        memory_lines=a.memory_lines,
        disk_lines_per_file=a.disk_lines_per_file,
        disk_file_count=a.disk_file_count,
        default=a.default,
    )


@router.get(
    "/{device_id}/logging/actions",
    response_model=list[LoggingActionPublic],
)
async def list_logging_actions(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[LoggingActionPublic]:
    device = await get_device(session, user.organization_id, device_id)
    try:
        items = await get_driver(device.vendor).system_logging_actions_list(
            _to_driver_creds(device)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e
    return [_action_to_public(a) for a in items]


@router.post(
    "/{device_id}/logging/actions",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_logging_action(
    device_id: UUID,
    payload: LoggingActionCreate,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    device = await get_device(session, user.organization_id, device_id)
    if payload.target == "remote" and not payload.remote:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="remote target requires a syslog server address",
        )
    try:
        new_id = await get_driver(device.vendor).system_logging_action_add(
            _to_driver_creds(device),
            name=payload.name,
            target=payload.target,
            remote=payload.remote,
            remote_port=payload.remote_port,
            src_address=payload.src_address,
            bsd_syslog=payload.bsd_syslog,
            syslog_facility=payload.syslog_facility,
            syslog_severity=payload.syslog_severity,
            memory_lines=payload.memory_lines,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="create_logging_action",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta={"action_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.delete(
    "/{device_id}/logging/actions/{action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_logging_action(
    device_id: UUID,
    action_id: str,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    device = await get_device(session, user.organization_id, device_id)
    try:
        await get_driver(device.vendor).system_logging_action_remove(
            _to_driver_creds(device), action_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)
        ) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="delete_logging_action",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"action_id": action_id},
    )
    await session.commit()
