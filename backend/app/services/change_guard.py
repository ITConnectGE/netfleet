"""The lockout guard: every firewall write on a Linux host goes through here.

A firewall change can sever the connection NetFleet manages the host over,
and the failure is silent and delayed. ufw accepts `ESTABLISHED,RELATED`
before it evaluates anything else, so the session that applied the change
survives, the command reports success, and it is the *next* connection that
fails — long after the action that caused it.

Two layers, and neither replaces the other:

* **A dead-man timer on the host.** Armed before the change, cancelled after
  it verifies. It lives on the managed host on purpose: it still fires when
  the thing that broke is the path between NetFleet and the host, or when
  this API process dies mid-change.
* **A fresh-connection probe.** `ssh_transport` closes its client after every
  batch, so there is no session left to test with — the probe opens a new one
  and that is exactly the thing the change might have broken. When it passes,
  the timer is cancelled immediately and the operator gets an answer in a
  second rather than in two minutes.

`run_guarded` is the only entry point a write should use. It refuses to run
at all on a host where the timer cannot be armed, because an unguarded write
that looks guarded is worse than one that is honestly refused.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.drivers.base import DeviceCredentials, ManagementPath
from app.models.change_guard import ChangeGuard, ChangeGuardState
from app.services.device import _to_driver_creds, get_device

log = structlog.get_logger(__name__)

# Long enough for a slow reconnect over a congested tunnel, short enough that
# a locked-out host is not unreachable for a coffee break.
DEFAULT_WINDOW_SECONDS = 120


class GuardUnavailable(Exception):
    """The host cannot arm a dead-man timer, so the write is refused.

    Deliberately fatal rather than a warning: a caller that proceeds anyway
    gets the appearance of a guard with none of the protection.
    """


class ChangeReverted(Exception):
    """The change applied, failed verification, and was undone.

    Carries whether NetFleet managed the rollback itself or is leaving it to
    the host's timer — the operator needs to know which, because the second
    means waiting.
    """

    def __init__(self, message: str, *, guard_id: UUID, restored_by_netfleet: bool):
        super().__init__(message)
        self.guard_id = guard_id
        self.restored_by_netfleet = restored_by_netfleet


async def management_path(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> ManagementPath:
    device = await get_device(session, organization_id, device_id)
    return await get_driver(device.vendor).management_path(_to_driver_creds(device))


async def run_guarded(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    kind: str,
    apply: Callable[[DeviceCredentials], Awaitable[Any]],
    started_by_user_id: UUID | None = None,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> tuple[ChangeGuard, Any]:
    """Arm, apply, verify. Returns the resolved guard and whatever `apply` did.

    Raises `ChangeReverted` when the host stopped answering afterwards. The
    change is undone in that case — either by this function or, if the host
    is genuinely unreachable, by the timer already ticking on it.
    """
    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    creds = _to_driver_creds(device)

    if not await driver.guard_supported(creds):
        raise GuardUnavailable(
            "this host has no systemd-run, so NetFleet cannot schedule the "
            "automatic rollback that firewall changes depend on. Refusing the "
            "change rather than making it unprotected."
        )

    token = uuid4().hex
    armed_at = datetime.now(UTC)
    snapshot_path = await driver.ufw_guard_arm(
        creds, token=token, window_seconds=window_seconds
    )

    guard = ChangeGuard(
        organization_id=organization_id,
        device_id=device_id,
        started_by_user_id=started_by_user_id,
        token=token,
        kind=kind,
        state=ChangeGuardState.ARMED,
        snapshot_path=snapshot_path,
        window_seconds=window_seconds,
        armed_at=armed_at,
        expires_at=armed_at + timedelta(seconds=window_seconds),
    )
    session.add(guard)
    # Committed before the change is applied, not after: if this process dies
    # between the two, the row must already name the armed timer.
    await session.commit()

    try:
        result = await apply(creds)
    except Exception:
        # The change itself failed, so the host is presumably fine — but a
        # timer is ticking on a snapshot that no longer needs restoring.
        # Disarm first and record second: the reverse order would leave a row
        # claiming to be resolved while the host still reverts itself.
        await _best_effort_cancel(driver, creds, token)
        await _resolve(
            session,
            guard,
            ChangeGuardState.ROLLED_BACK,
            "the change did not apply; the guard was disarmed and nothing was "
            "left behind on the host",
        )
        raise

    if await _reachable(driver, creds):
        await _best_effort_cancel(driver, creds, token)
        await _resolve(
            session, guard, ChangeGuardState.CONFIRMED, "verified on a new connection"
        )
        return guard, result

    # The host stopped answering. Try to undo it ourselves; the timer is the
    # fallback and is already running.
    log.warning(
        "change_guard.probe_failed", device_id=str(device_id), kind=kind, token=token
    )
    restored = False
    try:
        await driver.ufw_guard_restore(creds, token=token)
        restored = True
    except Exception as e:  # noqa: BLE001 - the timer covers us either way
        log.warning("change_guard.restore_failed", token=token, error=str(e)[:200])

    if restored:
        await _resolve(
            session,
            guard,
            ChangeGuardState.ROLLED_BACK,
            "the host stopped answering after the change; NetFleet restored "
            "the previous ruleset",
        )
        raise ChangeReverted(
            "The change was applied but this host stopped answering afterwards, "
            "so NetFleet restored the previous firewall configuration.",
            guard_id=guard.id,
            restored_by_netfleet=True,
        )

    seconds_left = max(
        0, int((guard.expires_at - datetime.now(UTC)).total_seconds())
    )
    raise ChangeReverted(
        "The change was applied but this host stopped answering, and NetFleet "
        f"cannot reach it to undo the change. The host will restore its "
        f"previous firewall configuration by itself in about {seconds_left}s.",
        guard_id=guard.id,
        restored_by_netfleet=False,
    )


async def confirm(
    session: AsyncSession, organization_id: UUID, guard_id: UUID
) -> ChangeGuard:
    """Manually disarm a guard left pending — the operator can see the host."""
    guard = await _get_armed(session, organization_id, guard_id)
    device = await get_device(session, organization_id, guard.device_id)
    driver = get_driver(device.vendor)
    await driver.ufw_guard_cancel(_to_driver_creds(device), token=guard.token)
    await _resolve(
        session, guard, ChangeGuardState.CONFIRMED, "confirmed by an operator"
    )
    return guard


async def rollback(
    session: AsyncSession, organization_id: UUID, guard_id: UUID
) -> ChangeGuard:
    """Restore the snapshot now, without waiting for the window to elapse."""
    guard = await _get_armed(session, organization_id, guard_id)
    device = await get_device(session, organization_id, guard.device_id)
    driver = get_driver(device.vendor)
    await driver.ufw_guard_restore(_to_driver_creds(device), token=guard.token)
    await _resolve(
        session,
        guard,
        ChangeGuardState.ROLLED_BACK,
        "rolled back by an operator",
    )
    return guard


async def list_pending(
    session: AsyncSession, organization_id: UUID, device_id: UUID | None = None
) -> list[ChangeGuard]:
    stmt = select(ChangeGuard).where(
        ChangeGuard.organization_id == organization_id,
        ChangeGuard.state == ChangeGuardState.ARMED,
    )
    if device_id is not None:
        stmt = stmt.where(ChangeGuard.device_id == device_id)
    return list((await session.execute(stmt.order_by(ChangeGuard.armed_at.desc()))).scalars())


async def expire_stale_guards(session: AsyncSession) -> int:
    """Close out guards whose window has passed.

    Mirrors `packages.mark_orphaned_runs`. The host restored itself when the
    timer fired; what NetFleet lost was the chance to observe it. A row that
    still claims to be armed a week later is worse than one that admits the
    window ran out.
    """
    result = await session.execute(
        update(ChangeGuard)
        .where(
            ChangeGuard.state == ChangeGuardState.ARMED,
            ChangeGuard.expires_at < datetime.now(UTC),
        )
        .values(
            state=ChangeGuardState.EXPIRED,
            resolved_at=datetime.now(UTC),
            detail="the confirmation window elapsed; the host restored its "
            "previous firewall configuration by itself",
        )
    )
    await session.commit()
    return result.rowcount or 0


# ---------------- internals ----------------


async def _reachable(driver, creds: DeviceCredentials) -> bool:
    """Open a brand-new connection. Command success proves nothing here —
    only that a fresh TCP connect and SSH auth still work."""
    try:
        return bool(await driver.test_connection(creds))
    except Exception:  # noqa: BLE001 - any failure means "cannot reach it"
        return False


async def _best_effort_cancel(driver, creds: DeviceCredentials, token: str) -> None:
    try:
        await driver.ufw_guard_cancel(creds, token=token)
    except Exception as e:  # noqa: BLE001
        # The timer will fire and restore a ruleset that is already correct,
        # which is noisy but not harmful. Worth a log, not an exception.
        log.warning("change_guard.cancel_failed", token=token, error=str(e)[:200])


async def _resolve(
    session: AsyncSession,
    guard: ChangeGuard,
    state: ChangeGuardState,
    detail: str,
) -> None:
    guard.state = state
    guard.resolved_at = datetime.now(UTC)
    guard.detail = detail
    await session.commit()


async def _get_armed(
    session: AsyncSession, organization_id: UUID, guard_id: UUID
) -> ChangeGuard:
    stmt = select(ChangeGuard).where(
        ChangeGuard.id == guard_id,
        ChangeGuard.organization_id == organization_id,
    )
    guard = (await session.execute(stmt)).scalar_one_or_none()
    if guard is None:
        raise GuardNotFound("no such change guard")
    if guard.state is not ChangeGuardState.ARMED:
        raise GuardNotArmed(
            f"this guard is already {guard.state.value} and cannot be changed"
        )
    return guard


class GuardNotFound(Exception):
    pass


class GuardNotArmed(Exception):
    pass
