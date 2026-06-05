"""Central log-event service — scrape device /log lines into a queryable table.

This is the "all my devices' criticals + errors in one place" inbox. The
scheduler calls `scan_org_devices_for_events` on a cadence; each device's
log buffer is pulled with topic=critical,error,warning (configurable), and
new lines are upserted by a content hash so re-polls don't duplicate.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from datetime import timedelta

from sqlalchemy import and_, delete, desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.drivers import get_driver
from app.models.device import Device
from app.models.device_log_event import (
    DeviceLogEvent,
    EventSeverity,
    EventSource,
)
from app.models.site import Site
from app.models.user import User
from app.services.device import _to_driver_creds

log = structlog.get_logger(__name__)


# Topics RouterOS exposes that mark the line's severity. Order matters —
# critical wins if both `critical` and `warning` appear. Lines that
# don't carry any of these explicit markers fall through to INFO so the
# unified inbox still picks them up (DHCP leases, IPsec key changes,
# system clock adjustments — useful when triaging "what was the box
# doing right before X").
_SEVERITY_TOPICS: list[tuple[str, EventSeverity]] = [
    ("critical", EventSeverity.CRITICAL),
    ("error", EventSeverity.ERROR),
    ("warning", EventSeverity.WARNING),
    ("info", EventSeverity.INFO),
]

# Empty default — pull every log line, then `_classify` decides the
# severity bucket. Previously we asked the device for
# "critical,error,warning" and the driver's broken substring filter
# combined with that to silently drop everything; the events page
# stayed empty even on noisy boxes. The five-minute poll cadence
# plus the 500-line per-device cap keeps the volume bounded.
DEFAULT_POLL_TOPICS = ""


def _classify(topics: str) -> EventSeverity | None:
    """Map a comma-separated topics string from RouterOS to our
    severity enum. The unified inbox keeps every log line — even
    unlabelled ones land in INFO — so an operator can review
    "everything the box said in the last hour" from one page."""
    parts = {t.strip().lower() for t in topics.split(",") if t.strip()}
    for keyword, severity in _SEVERITY_TOPICS:
        if keyword in parts:
            return severity
    return EventSeverity.INFO


def _dedup_key(device_time: str, topics: str, message: str) -> str:
    raw = f"{device_time}\x1f{topics}\x1f{message}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:32]


async def scan_device_for_events(
    session: AsyncSession,
    device: Device,
    *,
    tenant_id: UUID | None,
    topics: str = DEFAULT_POLL_TOPICS,
    limit: int = 500,
) -> int:
    """Pull the device's recent severity-tagged log lines and upsert any new
    ones. Returns the count of NEW rows persisted. Returns 0 if the device
    doesn't support log_list or if the call fails (which is logged but not
    raised — one device's flakiness shouldn't blow up the whole scan tick).
    """
    driver = get_driver(device.vendor)
    if not hasattr(driver, "log_list"):
        return 0
    try:
        lines = await driver.log_list(_to_driver_creds(device), topics=topics, limit=limit)
    except Exception as e:
        log.warning("events.device_scan_failed", device_id=str(device.id), error=str(e))
        return 0

    if not lines:
        return 0

    # Pre-build the rows so we can pass them to PostgreSQL's INSERT ... ON
    # CONFLICT DO NOTHING in a single statement.
    rows: list[dict[str, Any]] = []
    for line in lines:
        severity = _classify(line.topics)
        if severity is None:
            continue
        rows.append(
            {
                "organization_id": device.organization_id,
                "device_id": device.id,
                "tenant_id": tenant_id,
                "site_id": device.site_id,
                "device_time": line.time[:64],
                "severity": severity,
                "topics": line.topics[:255],
                "message": line.message,
                "source": EventSource.POLLED,
                "dedup_key": _dedup_key(line.time, line.topics, line.message),
            }
        )

    if not rows:
        return 0

    stmt = (
        pg_insert(DeviceLogEvent.__table__)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_device_log_events_dedup")
    )
    result = await session.execute(stmt)
    # rowcount reflects rows actually inserted (not skipped by ON CONFLICT).
    return int(result.rowcount or 0)


async def scan_org_devices_for_events(
    session: AsyncSession, organization_id: UUID, *, topics: str = DEFAULT_POLL_TOPICS
) -> tuple[int, int]:
    """Walk every enabled device and scan its logs. Returns (devices_scanned,
    new_events). Per-device failures are logged and skipped, not raised."""
    rows = list(
        (
            await session.execute(
                select(Device)
                .options(selectinload(Device.site))
                .where(
                    Device.organization_id == organization_id,
                    Device.is_enabled.is_(True),
                )
            )
        ).scalars().unique()
    )

    scanned = 0
    new_events = 0
    for d in rows:
        tenant_id = d.site.tenant_id if d.site is not None else None
        try:
            inserted = await scan_device_for_events(
                session, d, tenant_id=tenant_id, topics=topics
            )
            new_events += inserted
            scanned += 1
        except Exception as e:
            log.warning("events.org_scan_iteration_failed", device_id=str(d.id), error=str(e))
    return scanned, new_events


# ---------------- Query / acknowledge ----------------


async def list_events(
    session: AsyncSession,
    organization_id: UUID,
    *,
    severities: Iterable[EventSeverity] | None = None,
    device_id: UUID | None = None,
    tenant_id: UUID | None = None,
    site_id: UUID | None = None,
    acknowledged: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, int, dict[str, int]]:
    """Returns (rows, total_matching, total_unacknowledged_in_org, by_severity_counts)."""

    # Build a SELECT with the device / tenant / site / user joins flattened
    # into a single rowset so the API doesn't have to round-trip per row.
    from app.models.tenant import Tenant
    base = (
        select(
            DeviceLogEvent,
            Device.name.label("device_name"),
            Tenant.name.label("tenant_name"),
            Site.name.label("site_name"),
            User.email.label("acknowledged_by_email"),
        )
        .join(Device, Device.id == DeviceLogEvent.device_id)
        .outerjoin(Tenant, Tenant.id == DeviceLogEvent.tenant_id)
        .outerjoin(Site, Site.id == DeviceLogEvent.site_id)
        .outerjoin(User, User.id == DeviceLogEvent.acknowledged_by_user_id)
        .where(DeviceLogEvent.organization_id == organization_id)
    )

    if severities:
        sev_list = [s for s in severities]
        base = base.where(DeviceLogEvent.severity.in_(sev_list))
    if device_id is not None:
        base = base.where(DeviceLogEvent.device_id == device_id)
    if tenant_id is not None:
        base = base.where(DeviceLogEvent.tenant_id == tenant_id)
    if site_id is not None:
        base = base.where(DeviceLogEvent.site_id == site_id)
    if acknowledged is True:
        base = base.where(DeviceLogEvent.acknowledged_at.is_not(None))
    elif acknowledged is False:
        base = base.where(DeviceLogEvent.acknowledged_at.is_(None))
    if since is not None:
        base = base.where(DeviceLogEvent.observed_at >= since)
    if until is not None:
        base = base.where(DeviceLogEvent.observed_at <= until)
    if search:
        like = f"%{search}%"
        base = base.where(DeviceLogEvent.message.ilike(like))

    # Total count for paging
    count_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())

    # Rows
    rows_stmt = base.order_by(DeviceLogEvent.observed_at.desc()).limit(limit).offset(offset)
    rows = []
    for ev, device_name, tenant_name, site_name, ack_by_email in (
        await session.execute(rows_stmt)
    ).all():
        rows.append(
            {
                "id": ev.id,
                "organization_id": ev.organization_id,
                "device_id": ev.device_id,
                "device_name": device_name,
                "tenant_id": ev.tenant_id,
                "tenant_name": tenant_name,
                "site_id": ev.site_id,
                "site_name": site_name,
                "observed_at": ev.observed_at,
                "device_time": ev.device_time,
                "severity": ev.severity,
                "topics": ev.topics,
                "message": ev.message,
                "source": ev.source,
                "acknowledged_at": ev.acknowledged_at,
                "acknowledged_by_user_id": ev.acknowledged_by_user_id,
                "acknowledged_by_email": ack_by_email,
            }
        )

    # Org-wide unack + by_severity tallies (useful for header badge counters).
    unack_stmt = select(func.count()).where(
        DeviceLogEvent.organization_id == organization_id,
        DeviceLogEvent.acknowledged_at.is_(None),
    )
    unack_total = int((await session.execute(unack_stmt)).scalar_one())

    severity_counts_stmt = (
        select(DeviceLogEvent.severity, func.count())
        .where(
            DeviceLogEvent.organization_id == organization_id,
            DeviceLogEvent.acknowledged_at.is_(None),
        )
        .group_by(DeviceLogEvent.severity)
    )
    by_severity = {s.value: 0 for s in EventSeverity}
    for severity, count in (await session.execute(severity_counts_stmt)).all():
        by_severity[severity.value] = int(count)

    return rows, total, unack_total, by_severity


async def acknowledge_events(
    session: AsyncSession,
    organization_id: UUID,
    *,
    event_ids: list[UUID],
    user_id: UUID,
) -> int:
    if not event_ids:
        return 0
    stmt = (
        update(DeviceLogEvent)
        .where(
            and_(
                DeviceLogEvent.organization_id == organization_id,
                DeviceLogEvent.id.in_(event_ids),
                DeviceLogEvent.acknowledged_at.is_(None),
            )
        )
        .values(
            acknowledged_at=datetime.now(UTC),
            acknowledged_by_user_id=user_id,
        )
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


async def per_site_unack_summary(
    session: AsyncSession, organization_id: UUID
) -> dict[str, dict[str, int]]:
    """Return {site_id: {severity: count}} for unack events. Each
    severity is reported even when zero so the UI doesn't have to
    guess what severities are possible — keeps the response shape
    stable as we add tiers (info was added in v0.38, etc.)."""
    stmt = (
        select(
            DeviceLogEvent.site_id,
            DeviceLogEvent.severity,
            func.count(),
        )
        .where(
            DeviceLogEvent.organization_id == organization_id,
            DeviceLogEvent.acknowledged_at.is_(None),
            DeviceLogEvent.site_id.is_not(None),
        )
        .group_by(DeviceLogEvent.site_id, DeviceLogEvent.severity)
    )
    out: dict[str, dict[str, int]] = {}
    for site_id, severity, count in (await session.execute(stmt)).all():
        key = str(site_id)
        entry = out.setdefault(key, {s.value: 0 for s in EventSeverity})
        entry[severity.value] = int(count)
    return out


# ---------------- Retention ----------------


async def prune_events(
    session: AsyncSession,
    organization_id: UUID,
    *,
    max_age_days: int,
    max_rows: int,
) -> tuple[int, int]:
    """Drop events that are either too old or beyond the per-org row cap.

    Returns (rows_aged_out, rows_capped). Acknowledged rows are deleted
    just like unacknowledged ones — the events page is a rolling log
    feed, not a long-term archive (the per-device backup / audit log
    is). Both passes are cheap relative to the table size because the
    discriminator is the indexed `observed_at` column.
    """

    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    aged_stmt = delete(DeviceLogEvent).where(
        DeviceLogEvent.organization_id == organization_id,
        DeviceLogEvent.observed_at < cutoff,
    )
    aged = int((await session.execute(aged_stmt)).rowcount or 0)

    # Row-cap pass: count what's left, and if we're still over keep
    # only the newest `max_rows`. Implemented as a NOT IN subquery
    # rather than a CTE so it works on every Postgres ≥ 12.
    count_stmt = select(func.count()).where(
        DeviceLogEvent.organization_id == organization_id
    )
    total = int((await session.execute(count_stmt)).scalar_one())
    capped = 0
    if total > max_rows:
        keep_ids_stmt = (
            select(DeviceLogEvent.id)
            .where(DeviceLogEvent.organization_id == organization_id)
            .order_by(desc(DeviceLogEvent.observed_at))
            .limit(max_rows)
        )
        cap_stmt = delete(DeviceLogEvent).where(
            DeviceLogEvent.organization_id == organization_id,
            DeviceLogEvent.id.not_in(keep_ids_stmt),
        )
        capped = int((await session.execute(cap_stmt)).rowcount or 0)

    return aged, capped
