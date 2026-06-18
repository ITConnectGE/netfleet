"""Bulk operations across many devices in parallel."""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.drivers import get_driver
from app.drivers.base import DeviceCredentials, FilterRule, SnmpCommunity
from app.models.device import Device
from app.schemas.device_ops import BulkOperationResult
from app.services.device import _to_driver_creds

log = structlog.get_logger(__name__)


async def bulk_password_reset(
    session: AsyncSession,
    organization_id: UUID,
    *,
    device_ids: list[UUID],
    username: str,
    new_password: str,
) -> list[BulkOperationResult]:
    """Reset `username` to `new_password` across each device in `device_ids`."""
    # Resolve & validate ownership upfront
    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id, Device.id.in_(device_ids)
                )
            )
        ).scalars()
    )
    found = {d.id: d for d in devices}

    semaphore = asyncio.Semaphore(settings.POLLER_CONCURRENCY)

    async def run_one(device_id: UUID) -> BulkOperationResult:
        d = found.get(device_id)
        if d is None:
            return BulkOperationResult(
                device_id=device_id,
                device_name=None,
                status="skipped",
                error="device not found in organization",
            )
        if not d.is_enabled:
            return BulkOperationResult(
                device_id=device_id, device_name=d.name, status="skipped", error="device disabled"
            )
        async with semaphore:
            try:
                driver = get_driver(d.vendor)
                creds: DeviceCredentials = _to_driver_creds(d)
                await driver.device_user_set_password(creds, username, new_password)
                return BulkOperationResult(device_id=device_id, device_name=d.name, status="ok")
            except Exception as e:
                log.warning("bulk.password_reset.failed", device_id=str(device_id), error=str(e))
                return BulkOperationResult(
                    device_id=device_id, device_name=d.name, status="failed", error=str(e)
                )

    return await asyncio.gather(*(run_one(did) for did in device_ids))


# ---------------- Address-list (P21 #13) ----------------


async def bulk_address_list_add(
    session: AsyncSession,
    organization_id: UUID,
    *,
    device_ids: list[UUID],
    list_name: str,
    address: str,
    comment: str | None,
    timeout: str | None,
) -> list[BulkOperationResult]:
    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id,
                    Device.id.in_(device_ids),
                )
            )
        ).scalars()
    )
    found = {d.id: d for d in devices}

    semaphore = asyncio.Semaphore(settings.POLLER_CONCURRENCY)

    async def run_one(device_id: UUID) -> BulkOperationResult:
        d = found.get(device_id)
        if d is None:
            return BulkOperationResult(
                device_id=device_id,
                device_name=None,
                status="skipped",
                error="device not found in organization",
            )
        if not d.is_enabled:
            return BulkOperationResult(
                device_id=device_id,
                device_name=d.name,
                status="skipped",
                error="device disabled",
            )
        async with semaphore:
            try:
                driver = get_driver(d.vendor)
                creds = _to_driver_creds(d)
                await driver.firewall_address_list_add(
                    creds,
                    list_name=list_name,
                    address=address,
                    comment=comment,
                    timeout=timeout,
                )
                return BulkOperationResult(
                    device_id=device_id, device_name=d.name, status="ok"
                )
            except Exception as e:
                log.warning(
                    "bulk.address_list_add.failed",
                    device_id=str(device_id),
                    error=str(e),
                )
                return BulkOperationResult(
                    device_id=device_id,
                    device_name=d.name,
                    status="failed",
                    error=str(e),
                )

    return await asyncio.gather(*(run_one(did) for did in device_ids))


# ---------------- Firewall filter (P21 #13) ----------------


async def bulk_firewall_filter_add(
    session: AsyncSession,
    organization_id: UUID,
    *,
    device_ids: list[UUID],
    rule: FilterRule,
) -> list[BulkOperationResult]:
    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id,
                    Device.id.in_(device_ids),
                )
            )
        ).scalars()
    )
    found = {d.id: d for d in devices}

    semaphore = asyncio.Semaphore(settings.POLLER_CONCURRENCY)

    async def run_one(device_id: UUID) -> BulkOperationResult:
        d = found.get(device_id)
        if d is None:
            return BulkOperationResult(
                device_id=device_id,
                device_name=None,
                status="skipped",
                error="device not found in organization",
            )
        if not d.is_enabled:
            return BulkOperationResult(
                device_id=device_id,
                device_name=d.name,
                status="skipped",
                error="device disabled",
            )
        async with semaphore:
            try:
                driver = get_driver(d.vendor)
                creds = _to_driver_creds(d)
                await driver.firewall_filter_add(creds, rule)
                return BulkOperationResult(
                    device_id=device_id, device_name=d.name, status="ok"
                )
            except Exception as e:
                log.warning(
                    "bulk.firewall_filter_add.failed",
                    device_id=str(device_id),
                    error=str(e),
                )
                return BulkOperationResult(
                    device_id=device_id,
                    device_name=d.name,
                    status="failed",
                    error=str(e),
                )

    return await asyncio.gather(*(run_one(did) for did in device_ids))


# ---------------- Zabbix SNMP setup (wizard) ----------------


async def bulk_zabbix_snmp_setup(
    session: AsyncSession,
    organization_id: UUID,
    *,
    device_ids: list[UUID],
    zabbix_addresses: list[str],
    address_list_name: str,
    firewall_chain: str,
    snmp_port: int,
    community_name: str,
    configure_community: bool,
    lock_service_address: bool,
    comment_tag: str,
) -> list[BulkOperationResult]:
    """Provision SNMP-for-Zabbix across many devices in one parallel pass.

    Per device, idempotently:
      1. add each Zabbix source IP to the ``address_list_name`` address-list,
      2. add (if missing, keyed on ``comment_tag``) an accept rule for
         UDP/``snmp_port`` sourced from that list, moved to the top of the
         chain so it wins over any catch-all drop below,
      3. (optional) point the SNMP community at the Zabbix IPs, read-only,
      4. enable SNMP globally and the ``/ip/service snmp`` entry, optionally
         locking its address whitelist to the Zabbix IPs.

    Re-running is safe: duplicate address-list entries are swallowed, the
    firewall rule is matched by comment, and the community/service are updated
    in place.
    """
    devices = list(
        (
            await session.execute(
                select(Device).where(
                    Device.organization_id == organization_id,
                    Device.id.in_(device_ids),
                )
            )
        ).scalars()
    )
    found = {d.id: d for d in devices}
    addr_csv = ",".join(zabbix_addresses)

    semaphore = asyncio.Semaphore(settings.POLLER_CONCURRENCY)

    async def run_one(device_id: UUID) -> BulkOperationResult:
        d = found.get(device_id)
        if d is None:
            return BulkOperationResult(
                device_id=device_id,
                device_name=None,
                status="skipped",
                error="device not found in organization",
            )
        if not d.is_enabled:
            return BulkOperationResult(
                device_id=device_id,
                device_name=d.name,
                status="skipped",
                error="device disabled",
            )

        done: list[str] = []
        async with semaphore:
            driver = get_driver(d.vendor)
            creds = _to_driver_creds(d)
            try:
                # 1. Zabbix IP(s) -> address-list (idempotent: ignore dupes).
                for addr in zabbix_addresses:
                    try:
                        await driver.firewall_address_list_add(
                            creds,
                            list_name=address_list_name,
                            address=addr,
                            comment=comment_tag,
                            timeout=None,
                        )
                    except Exception as e:  # noqa: BLE001
                        if "already have such entry" not in str(e).lower():
                            raise
                done.append(f"address-list({len(zabbix_addresses)})")

                # 2. Accept rule for SNMP, matched/owned by comment_tag.
                rules = await driver.firewall_filter_list(creds)
                existing = next(
                    (
                        r
                        for r in rules
                        if r.chain == firewall_chain and (r.comment or "") == comment_tag
                    ),
                    None,
                )
                if existing is None:
                    new_id = await driver.firewall_filter_add(
                        creds,
                        FilterRule(
                            id=None,
                            chain=firewall_chain,
                            action="accept",
                            protocol="udp",
                            dst_port=str(snmp_port),
                            src_address_list=address_list_name,
                            comment=comment_tag,
                            disabled=False,
                        ),
                    )
                    # Push it above the first existing rule in the chain so it
                    # precedes any catch-all drop. Best-effort: the rule is
                    # already in place even if the move fails.
                    first_in_chain = next(
                        (r for r in rules if r.chain == firewall_chain and r.id), None
                    )
                    if new_id and first_in_chain and first_in_chain.id:
                        try:
                            await driver.firewall_filter_move(
                                creds, new_id, before_id=first_in_chain.id
                            )
                        except Exception:  # noqa: BLE001
                            pass
                    done.append("firewall(new)")
                else:
                    if existing.disabled and existing.id:
                        await driver.firewall_filter_set(
                            creds, existing.id, disabled=False
                        )
                    done.append("firewall(exists)")

                # 3. SNMP community pointed at Zabbix, read-only.
                if configure_community:
                    comms = await driver.snmp_community_list(creds)
                    match = next((c for c in comms if c.name == community_name), None)
                    if match and match.id:
                        await driver.snmp_community_update(
                            creds,
                            match.id,
                            addresses=addr_csv,
                            read_access=True,
                            write_access=False,
                            disabled=False,
                        )
                        done.append("community(updated)")
                    else:
                        await driver.snmp_community_add(
                            creds,
                            SnmpCommunity(
                                id=None,
                                name=community_name,
                                addresses=addr_csv,
                                read_access=True,
                                write_access=False,
                            ),
                        )
                        done.append("community(new)")

                # 4. Enable SNMP globally + the /ip/service snmp entry.
                await driver.snmp_set(creds, enabled=True)
                await driver.ip_service_set(
                    creds,
                    "snmp",
                    enabled=True,
                    port=snmp_port,
                    address=addr_csv if lock_service_address else None,
                )
                done.append("service")

                return BulkOperationResult(
                    device_id=device_id,
                    device_name=d.name,
                    status="ok",
                    detail=", ".join(done),
                )
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "bulk.zabbix_snmp_setup.failed",
                    device_id=str(device_id),
                    error=str(e),
                    done=done,
                )
                return BulkOperationResult(
                    device_id=device_id,
                    device_name=d.name,
                    status="failed",
                    error=str(e),
                    detail=("done: " + ", ".join(done)) if done else None,
                )

    return await asyncio.gather(*(run_one(did) for did in device_ids))
