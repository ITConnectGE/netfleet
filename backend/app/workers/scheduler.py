"""Worker scheduler — runs daily fleet jobs (backups, retention, future firmware checks).

Each job declares its interval in seconds. On startup all jobs run once, then
re-fire on their cadence. Jobs are run sequentially per tick so a slow backup
job doesn't pile up on top of itself.
"""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session, init_db
from app.core.logging import configure_logging
from app.models.organization import Organization
from app.services import backups as backup_svc
from app.services import events as events_svc
from app.services import firmware as firmware_svc

log = structlog.get_logger("netfleet.scheduler")


Job = Callable[[AsyncSession], Awaitable[None]]


@dataclass(slots=True)
class ScheduledJob:
    name: str
    interval_seconds: int
    handler: Job


# ---------------- Jobs ----------------


async def job_nightly_backups(session: AsyncSession) -> None:
    """Backup every enabled device of every org once a day."""
    orgs = list((await session.execute(select(Organization))).scalars())
    for org in orgs:
        log.info("scheduler.backups.start", organization_id=str(org.id))
        rows = await backup_svc.backup_all_devices(session, org.id)
        await session.commit()
        ok = sum(1 for r in rows if r.status.value == "ok")
        failed = sum(1 for r in rows if r.status.value == "failed")
        log.info(
            "scheduler.backups.done",
            organization_id=str(org.id),
            attempted=len(rows),
            ok=ok,
            failed=failed,
        )


async def job_firmware_check(session: AsyncSession) -> None:
    """Refresh firmware-update status for every enabled device, every org."""
    orgs = list((await session.execute(select(Organization))).scalars())
    for org in orgs:
        ok, failed = await firmware_svc.check_fleet_firmware(session, org.id)
        await session.commit()
        log.info(
            "scheduler.firmware_check.done",
            organization_id=str(org.id),
            ok=ok,
            failed=failed,
        )


async def job_scan_log_events(session: AsyncSession) -> None:
    """Pull severity-tagged log lines from every device into the central
    event inbox. Runs every NETFLEET_EVENT_SCAN_INTERVAL_SECONDS (default
    5 min). Per-device failures are absorbed by the service."""
    orgs = list((await session.execute(select(Organization))).scalars())
    for org in orgs:
        scanned, new = await events_svc.scan_org_devices_for_events(session, org.id)
        await session.commit()
        if new:
            log.info(
                "scheduler.events_scan.done",
                organization_id=str(org.id),
                devices_scanned=scanned,
                new_events=new,
            )


async def job_firmware_auto_upgrade(session: AsyncSession) -> None:
    """Walk per-device auto-upgrade policy and trigger upgrades whose window
    contains the current UTC hour. Devices that already have a pending
    upgrade are skipped — the post-upgrade firmware-check will reconcile
    pending→succeeded when the new version is installed."""
    orgs = list((await session.execute(select(Organization))).scalars())
    for org in orgs:
        eligible, upgraded, failed = await firmware_svc.auto_upgrade_run(session, org.id)
        await session.commit()
        if eligible or upgraded or failed:
            log.info(
                "scheduler.firmware_auto_upgrade.done",
                organization_id=str(org.id),
                eligible=eligible,
                upgraded=upgraded,
                failed=failed,
            )


async def job_event_retention(session: AsyncSession) -> None:
    """Drop events older than EVENT_RETENTION_DAYS plus everything past
    EVENT_MAX_ROWS_PER_ORG (newest kept). Runs hourly; both passes are
    cheap relative to the table because the discriminator is the
    indexed observed_at column."""
    orgs = list((await session.execute(select(Organization))).scalars())
    for org in orgs:
        aged, capped = await events_svc.prune_events(
            session,
            org.id,
            max_age_days=settings.EVENT_RETENTION_DAYS,
            max_rows=settings.EVENT_MAX_ROWS_PER_ORG,
        )
        await session.commit()
        if aged or capped:
            log.info(
                "scheduler.event_retention.done",
                organization_id=str(org.id),
                aged_out=aged,
                row_capped=capped,
            )


async def job_backup_retention(session: AsyncSession) -> None:
    """Apply retention to every org's backup history."""
    keep_days = int(os.environ.get("NETFLEET_BACKUP_RETENTION_DAYS", "30"))
    orgs = list((await session.execute(select(Organization))).scalars())
    for org in orgs:
        removed = await backup_svc.apply_retention(session, org.id, keep_days=keep_days)
        await session.commit()
        if removed:
            log.info(
                "scheduler.retention.removed",
                organization_id=str(org.id),
                files=removed,
                keep_days=keep_days,
            )


JOBS: list[ScheduledJob] = [
    ScheduledJob(
        name="nightly-backups",
        interval_seconds=int(os.environ.get("NETFLEET_BACKUP_INTERVAL_SECONDS", str(24 * 3600))),
        handler=job_nightly_backups,
    ),
    ScheduledJob(
        name="backup-retention",
        interval_seconds=int(os.environ.get("NETFLEET_RETENTION_INTERVAL_SECONDS", str(24 * 3600))),
        handler=job_backup_retention,
    ),
    ScheduledJob(
        name="firmware-check",
        interval_seconds=int(os.environ.get("NETFLEET_FIRMWARE_INTERVAL_SECONDS", str(24 * 3600))),
        handler=job_firmware_check,
    ),
    ScheduledJob(
        name="firmware-auto-upgrade",
        # Hourly — so the per-device window can be acted on within the hour
        # it opens. Devices outside the window are skipped cheaply.
        interval_seconds=int(os.environ.get("NETFLEET_AUTO_UPGRADE_INTERVAL_SECONDS", str(3600))),
        handler=job_firmware_auto_upgrade,
    ),
    ScheduledJob(
        name="event-scan",
        # 5 min by default — short enough that critical events surface
        # quickly, long enough that 100 devices is a manageable rate.
        interval_seconds=int(os.environ.get("NETFLEET_EVENT_SCAN_INTERVAL_SECONDS", str(300))),
        handler=job_scan_log_events,
    ),
    ScheduledJob(
        name="event-retention",
        # Hourly. The cap query is `count + DELETE ... NOT IN` which
        # is fine at 500k rows but not free, so we don't run it more
        # often than we have to.
        interval_seconds=int(
            os.environ.get("NETFLEET_EVENT_RETENTION_INTERVAL_SECONDS", str(3600))
        ),
        handler=job_event_retention,
    ),
]


# ---------------- Loop ----------------


async def _run_once(job: ScheduledJob) -> None:
    async for session in get_session():
        try:
            await job.handler(session)
        except Exception as e:
            log.exception("scheduler.job_failed", job=job.name, error=str(e))
        return  # consume the single yielded session and exit


async def main() -> None:
    configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    await init_db()
    log.info("scheduler.start", jobs=[j.name for j in JOBS])

    stopping = asyncio.Event()

    def _stop(signum: int, _: object) -> None:
        log.info("scheduler.signal", signum=signum)
        stopping.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop, sig, None)
        except NotImplementedError:
            signal.signal(sig, _stop)  # Windows dev fallback

    next_at: dict[str, float] = {j.name: 0.0 for j in JOBS}

    while not stopping.is_set():
        now = loop.time()
        for job in JOBS:
            if now >= next_at[job.name]:
                log.info("scheduler.tick", job=job.name)
                await _run_once(job)
                next_at[job.name] = loop.time() + job.interval_seconds

        # Sleep until the next scheduled fire, but wake every 30s to check signals.
        soonest = min(next_at.values()) - loop.time()
        try:
            await asyncio.wait_for(stopping.wait(), timeout=max(1.0, min(soonest, 30.0)))
        except asyncio.TimeoutError:
            pass

    log.info("scheduler.shutdown")


if __name__ == "__main__":
    asyncio.run(main())
