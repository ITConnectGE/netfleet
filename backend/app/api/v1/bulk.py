"""Bulk operations endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, require_permission
from app.drivers.base import FilterRule
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.device_ops import (
    BulkAddressListAddRequest,
    BulkAddressListAddResponse,
    BulkFirewallFilterRequest,
    BulkFirewallFilterResponse,
    BulkPasswordResetRequest,
    BulkPasswordResetResponse,
    BulkZabbixSnmpSetupRequest,
    BulkZabbixSnmpSetupResponse,
)
from app.services import audit as audit_svc
from app.services import bulk as bulk_svc

router = APIRouter()


@router.post(
    "/device-users/password-reset",
    response_model=BulkPasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_device_user_password_reset(
    payload: BulkPasswordResetRequest,
    request: Request,
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> BulkPasswordResetResponse:
    results = await bulk_svc.bulk_password_reset(
        session,
        user.organization_id,
        device_ids=payload.device_ids,
        username=payload.username,
        new_password=payload.new_password,
    )

    succeeded = sum(1 for r in results if r.status == "ok")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")

    # Single audit row for the whole bulk operation
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.user",
        action="bulk_reset_password",
        outcome=AuditOutcome.OK if failed == 0 else AuditOutcome.FAILED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "target_username": payload.username,
            "device_count": len(payload.device_ids),
        },
        response_meta={
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        },
    )
    await session.commit()

    return BulkPasswordResetResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        results=results,
    )


@router.post(
    "/firewall/address-list/add",
    response_model=BulkAddressListAddResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_address_list_add(
    payload: BulkAddressListAddRequest,
    request: Request,
    user: User = Depends(require_permission("firewall.filter", "write")),
    session: AsyncSession = Depends(db_session),
) -> BulkAddressListAddResponse:
    results = await bulk_svc.bulk_address_list_add(
        session,
        user.organization_id,
        device_ids=payload.device_ids,
        list_name=payload.list_name,
        address=payload.address,
        comment=payload.comment,
        timeout=payload.timeout,
    )
    succeeded = sum(1 for r in results if r.status == "ok")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.filter",
        action="bulk_address_list_add",
        outcome=AuditOutcome.OK if failed == 0 else AuditOutcome.FAILED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "list_name": payload.list_name,
            "address": payload.address,
            "device_count": len(payload.device_ids),
            "timeout": payload.timeout,
        },
        response_meta={
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        },
    )
    await session.commit()
    return BulkAddressListAddResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        results=results,
    )


@router.post(
    "/firewall/filter/add",
    response_model=BulkFirewallFilterResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_firewall_filter_add(
    payload: BulkFirewallFilterRequest,
    request: Request,
    user: User = Depends(require_permission("firewall.filter", "write")),
    session: AsyncSession = Depends(db_session),
) -> BulkFirewallFilterResponse:
    rule = FilterRule(
        id=None,
        chain=payload.rule.chain,
        action=payload.rule.action,
        src_address=payload.rule.src_address,
        dst_address=payload.rule.dst_address,
        src_address_list=payload.rule.src_address_list,
        dst_address_list=payload.rule.dst_address_list,
        protocol=payload.rule.protocol,
        src_port=payload.rule.src_port,
        dst_port=payload.rule.dst_port,
        in_interface=payload.rule.in_interface,
        out_interface=payload.rule.out_interface,
        connection_state=payload.rule.connection_state,
        log=payload.rule.log,
        log_prefix=payload.rule.log_prefix,
        disabled=payload.rule.disabled,
        comment=payload.rule.comment,
    )
    results = await bulk_svc.bulk_firewall_filter_add(
        session,
        user.organization_id,
        device_ids=payload.device_ids,
        rule=rule,
    )
    succeeded = sum(1 for r in results if r.status == "ok")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.filter",
        action="bulk_firewall_filter_add",
        outcome=AuditOutcome.OK if failed == 0 else AuditOutcome.FAILED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "chain": payload.rule.chain,
            "action": payload.rule.action,
            "device_count": len(payload.device_ids),
        },
        response_meta={
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        },
    )
    await session.commit()
    return BulkFirewallFilterResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        results=results,
    )


@router.post(
    "/zabbix-snmp/setup",
    response_model=BulkZabbixSnmpSetupResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_zabbix_snmp_setup(
    payload: BulkZabbixSnmpSetupRequest,
    request: Request,
    user: User = Depends(require_permission("firewall.filter", "write")),
    session: AsyncSession = Depends(db_session),
) -> BulkZabbixSnmpSetupResponse:
    results = await bulk_svc.bulk_zabbix_snmp_setup(
        session,
        user.organization_id,
        device_ids=payload.device_ids,
        zabbix_addresses=payload.zabbix_addresses,
        address_list_name=payload.address_list_name,
        firewall_chain=payload.firewall_chain,
        snmp_port=payload.snmp_port,
        community_name=payload.community_name,
        configure_community=payload.configure_community,
        lock_service_address=payload.lock_service_address,
        comment_tag=payload.comment_tag,
    )
    succeeded = sum(1 for r in results if r.status == "ok")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.filter",
        action="bulk_zabbix_snmp_setup",
        outcome=AuditOutcome.OK if failed == 0 else AuditOutcome.FAILED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "zabbix_addresses": payload.zabbix_addresses,
            "address_list_name": payload.address_list_name,
            "community_name": payload.community_name if payload.configure_community else None,
            "snmp_port": payload.snmp_port,
            "lock_service_address": payload.lock_service_address,
            "device_count": len(payload.device_ids),
        },
        response_meta={
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        },
    )
    await session.commit()
    return BulkZabbixSnmpSetupResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        results=results,
    )
