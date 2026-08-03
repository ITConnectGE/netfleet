"""Package operations, including the long-running ones.

An upgrade takes minutes to tens of minutes. Rather than hold an HTTP
request open for that, the endpoint records a `PackageRun`, starts a
background task, and returns the row for the UI to poll.

The background task owns its own database session: the request's session
is closed the moment the response is sent, and reusing it would fail on
the first write after that.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_factory
from app.drivers import get_driver
from app.drivers.base import PackageState, UnsupportedOperation
from app.models.device import Device, DeviceClass
from app.models.package_run import PackageRun, PackageRunKind, PackageRunState
from app.services.device import HostKeyNotPinned, _to_driver_creds, get_device

log = structlog.get_logger(__name__)

# Enough to diagnose a failure, small enough that a runaway upgrade log
# cannot bloat the table. The tail matters more than the head — errors
# land at the end.
MAX_OUTPUT_CHARS = 64_000


class PackageRunInProgress(Exception):
    """Refused: this device already has a package operation running.

    Two `apt-get` processes on one host would deadlock on the dpkg lock and
    leave both looking hung, so the second is refused up front with a
    reason rather than started and left to fail obscurely.
    """


def _tail(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return "…output truncated…\n" + text[-MAX_OUTPUT_CHARS:]


async def get_state(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> PackageState:
    """Read package state from the host and cache the summary on the device.

    Caching here rather than only in the scheduler means opening a host's
    Packages tab also refreshes what the fleet overview shows for it —
    otherwise the two screens disagree and the overview looks broken.
    """
    device = await get_device(session, organization_id, device_id)
    try:
        state = await get_driver(device.vendor).packages_state(_to_driver_creds(device))
    except Exception as e:
        # Record the failure so the overview can say "could not check"
        # rather than showing a silently stale number.
        device.packages_check_error = str(e)[:1024]
        device.packages_checked_at = datetime.now(UTC)
        await session.commit()
        raise

    _apply_state(device, state)
    await session.commit()
    return state


def _apply_state(device, state: PackageState) -> None:
    device.packages_manager = state.manager
    device.packages_updates_count = len(state.updates)
    device.packages_security_count = state.security_count
    device.packages_reboot_required = state.reboot_required
    device.packages_checked_at = datetime.now(UTC)
    device.packages_check_error = None


async def refresh_fleet_packages(
    session: AsyncSession, organization_id: UUID
) -> tuple[int, int]:
    """Refresh cached counts for every enabled server in an organisation.

    Sequential on purpose: this runs unattended against every host an MSP
    manages, and a burst of concurrent SSH sessions is exactly the kind of
    thing that trips fail2ban or an IDS at three in the morning.
    """
    stmt = select(Device).where(
        Device.organization_id == organization_id,
        Device.device_class == DeviceClass.SERVER,
        Device.is_enabled.is_(True),
    )
    devices = list((await session.execute(stmt)).scalars())

    ok = failed = 0
    for device in devices:
        try:
            state = await get_driver(device.vendor).packages_state(
                _to_driver_creds(device)
            )
        except Exception as e:  # noqa: BLE001 - one bad host must not stop the sweep
            device.packages_check_error = str(e)[:1024]
            device.packages_checked_at = datetime.now(UTC)
            failed += 1
            log.info(
                "packages.fleet_refresh.device_failed",
                device_id=str(device.id),
                error=str(e)[:200],
            )
            continue
        _apply_state(device, state)
        ok += 1

    await session.commit()
    return ok, failed


async def list_runs(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    limit: int = 20,
) -> list[PackageRun]:
    stmt = (
        select(PackageRun)
        .where(
            PackageRun.organization_id == organization_id,
            PackageRun.device_id == device_id,
        )
        .order_by(PackageRun.started_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars())


async def _active_run(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> PackageRun | None:
    stmt = select(PackageRun).where(
        PackageRun.organization_id == organization_id,
        PackageRun.device_id == device_id,
        PackageRun.state == PackageRunState.RUNNING,
    )
    return (await session.execute(stmt)).scalars().first()


async def start_run(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    kind: PackageRunKind,
    packages: list[str] | None = None,
    security_only: bool = False,
    started_by_user_id: UUID | None = None,
) -> PackageRun:
    """Record the run and kick off the work. Returns immediately."""
    device = await get_device(session, organization_id, device_id)

    existing = await _active_run(session, organization_id, device_id)
    if existing is not None:
        raise PackageRunInProgress(
            f"a {existing.kind.value} is already running on this host "
            "(dpkg allows only one at a time)"
        )

    run = PackageRun(
        organization_id=organization_id,
        device_id=device_id,
        started_by_user_id=started_by_user_id,
        kind=kind,
        state=PackageRunState.RUNNING,
        packages=",".join(packages) if packages else None,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    vendor = device.vendor
    creds = _to_driver_creds(device)
    await session.commit()

    # Deliberately not awaited. The reference is kept so the loop cannot
    # garbage-collect the task mid-flight.
    task = asyncio.create_task(
        _execute(run_id, vendor, creds, kind, packages, security_only)
    )
    _RUNNING.add(task)
    task.add_done_callback(_RUNNING.discard)
    return run


_RUNNING: set[asyncio.Task] = set()


async def _execute(
    run_id: UUID,
    vendor: str,
    creds,
    kind: PackageRunKind,
    packages: list[str] | None,
    security_only: bool,
) -> None:
    driver = get_driver(vendor)
    state = PackageRunState.SUCCEEDED
    output = ""
    error: str | None = None
    try:
        if kind is PackageRunKind.REFRESH:
            output = await driver.packages_refresh(creds)
        else:
            output = await driver.packages_upgrade(
                creds, names=packages, security_only=security_only
            )
    except (UnsupportedOperation, HostKeyNotPinned) as e:
        state, error = PackageRunState.FAILED, str(e)
    except Exception as e:  # noqa: BLE001 - the reason belongs on the row
        state, error = PackageRunState.FAILED, str(e)[:2000]
        log.warning("packages.run.failed", run_id=str(run_id), error=str(e))

    # A fresh session: the request's was closed when its response was sent.
    async with session_factory()() as session:
        await session.execute(
            update(PackageRun)
            .where(PackageRun.id == run_id)
            .values(
                state=state,
                finished_at=datetime.now(UTC),
                output=_tail(output),
                error=error,
            )
        )
        await session.commit()


async def mark_orphaned_runs(session: AsyncSession) -> int:
    """Close out runs left `running` by an API restart.

    The command may well have finished on the host — what ended was our
    ability to watch it. A row that still claims to be running months
    later is worse than one that admits we lost track.
    """
    result = await session.execute(
        update(PackageRun)
        .where(PackageRun.state == PackageRunState.RUNNING)
        .values(
            state=PackageRunState.INTERRUPTED,
            finished_at=datetime.now(UTC),
            error="the API restarted while this was running; "
            "check the host to see whether it completed",
        )
    )
    await session.commit()
    return result.rowcount or 0
