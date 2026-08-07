"""UFW service.

Every write here goes through `change_guard.run_guarded`. None of them may
call the driver directly — see docs/UFW-SSH-PLAN.md before adding one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.drivers.base import UfwRule, UfwRuleSpec, UfwStatus, UnsupportedOperation
from app.drivers.linux import _ufw_rule_from_spec as _rule_from_spec
from app.drivers.linux import (
    ufw_project_deleted,
    ufw_project_inserted,
    ufw_project_moved,
    ufw_project_replaced,
    ufw_projected_rule,
    ufw_would_lock_out,
)
from app.models.change_guard import ChangeGuard
from app.models.ufw_disabled_rule import UfwDisabledRule
from app.services import change_guard as guard_svc
from app.services.device import HostKeyNotPinned, _to_driver_creds, get_device

log = structlog.get_logger(__name__)


class OperationError(Exception):
    pass


class WouldLockOut(Exception):
    """Refused: this is the only rule keeping NetFleet able to reach the host.

    Overridable with `force`, because an operator at the console may know
    something NetFleet does not — but never by default, and never silently.
    """


async def get_status(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> UfwStatus:
    device = await get_device(session, organization_id, device_id)
    try:
        return await get_driver(device.vendor).ufw_status(_to_driver_creds(device))
    except (UnsupportedOperation, HostKeyNotPinned):
        # These carry their own HTTP mapping (501 / 409). Wrapping them in
        # OperationError would flatten both into a 502 that blames the host
        # for a request that never should have reached it.
        raise
    except Exception as e:
        raise OperationError(str(e)) from e


# ---------------- management-path protection ----------------


async def _assert_change_is_safe(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    project: Callable[[list[UfwRule]], list[UfwRule]],
    what: str,
) -> None:
    """Simulate the ruleset this change would leave behind, and refuse it if
    NetFleet would no longer be able to reach the host.

    Order matters as much as membership: ufw is first-match, so a deny moved
    *above* the allow that keeps NetFleet reachable takes the host away
    without deleting anything. `project` returns the rules in the order they
    would end up in, and the verdict is read by walking them.

    The host-side guard would catch the lockout and undo it either way — but
    only after up to two minutes of an unreachable host, and with no
    explanation of what went wrong. Refusing up front is cheaper and can name
    the cause.
    """
    path = await guard_svc.management_path(session, organization_id, device_id)
    if not path.known:
        # Nothing observed, nothing to reason about. The guard is the backstop.
        return

    status = await get_status(session, organization_id, device_id)
    if not status.active:
        # Nothing is being enforced, so no reordering can cut anything.
        return
    if ufw_would_lock_out(status.rules, path, status.default_incoming):
        # Already unreachable by this reasoning, yet here we are talking to it.
        # The model is wrong about this host, so it has no business blocking a
        # change on the strength of it.
        log.info(
            "ufw.safety_check.skipped",
            device_id=str(device_id),
            reason="current ruleset already reads as locked out",
        )
        return

    if ufw_would_lock_out(project(status.rules), path, status.default_incoming):
        raise WouldLockOut(
            f"{what} would stop NetFleet reaching this host "
            f"({path.client_address} → port {path.server_port}), leaving it "
            "unmanageable. Add a rule that keeps that path open first, or "
            "repeat the request with force if you have another way in."
        )


# ---------------- writes ----------------


async def add_rule(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    spec: UfwRuleSpec,
    *,
    position: int | None = None,
    started_by_user_id: UUID | None = None,
) -> tuple[ChangeGuard, str]:
    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    return await guard_svc.run_guarded(
        session,
        organization_id,
        device_id,
        kind="ufw.rule.add",
        started_by_user_id=started_by_user_id,
        apply=lambda creds: driver.ufw_rule_add(creds, spec, position=position),
    )


async def delete_rule(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    spec: str,
    force: bool = False,
    started_by_user_id: UUID | None = None,
) -> tuple[ChangeGuard, str]:
    if not force:
        await _assert_change_is_safe(
            session,
            organization_id,
            device_id,
            project=lambda rules: ufw_project_deleted(rules, spec),
            what="Deleting this rule",
        )

    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    return await guard_svc.run_guarded(
        session,
        organization_id,
        device_id,
        kind="ufw.rule.delete",
        started_by_user_id=started_by_user_id,
        apply=lambda creds: driver.ufw_rule_delete(creds, spec=spec),
    )


async def edit_rule(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    old_spec: str,
    spec: UfwRuleSpec,
    position: int | None = None,
    force: bool = False,
    started_by_user_id: UUID | None = None,
) -> tuple[ChangeGuard, str]:
    if not force:
        await _assert_change_is_safe(
            session,
            organization_id,
            device_id,
            project=lambda rules: ufw_project_replaced(
                rules, old_spec, ufw_projected_rule(spec), position
            ),
            what="This edit",
        )

    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    return await guard_svc.run_guarded(
        session,
        organization_id,
        device_id,
        kind="ufw.rule.edit",
        started_by_user_id=started_by_user_id,
        apply=lambda creds: driver.ufw_rule_replace(
            creds, old_spec=old_spec, new_spec=spec, position=position
        ),
    )


async def list_disabled(
    session: AsyncSession, organization_id: UUID, device_id: UUID
) -> list[UfwDisabledRule]:
    stmt = (
        select(UfwDisabledRule)
        .where(
            UfwDisabledRule.organization_id == organization_id,
            UfwDisabledRule.device_id == device_id,
        )
        .order_by(UfwDisabledRule.position.nulls_last(), UfwDisabledRule.disabled_at)
    )
    return list((await session.execute(stmt)).scalars())


async def disable_rule(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    spec: str,
    force: bool = False,
    started_by_user_id: UUID | None = None,
) -> tuple[ChangeGuard, str]:
    """Switch a rule off: remove it from the host, remember it here.

    ufw has no disabled state, so this is a delete plus a record of how to put
    it back. The record is written only after the host confirms the removal —
    the reverse order would leave NetFleet claiming a rule is disabled when it
    is still being enforced.
    """
    status = await get_status(session, organization_id, device_id)
    target = next((r for r in status.rules if r.spec == spec), None)
    if target is None:
        raise OperationError(
            "that rule is no longer in the ruleset — reload and try again"
        )

    if not force:
        await _assert_change_is_safe(
            session,
            organization_id,
            device_id,
            project=lambda rules: ufw_project_deleted(rules, spec),
            what="Disabling this rule",
        )

    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    guard, command = await guard_svc.run_guarded(
        session,
        organization_id,
        device_id,
        kind="ufw.rule.disable",
        started_by_user_id=started_by_user_id,
        apply=lambda creds: driver.ufw_rule_delete(creds, spec=spec),
    )

    session.add(
        UfwDisabledRule(
            organization_id=organization_id,
            device_id=device_id,
            disabled_by_user_id=started_by_user_id,
            spec=spec,
            position=target.position,
            disabled_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return guard, command


async def enable_rule(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    disabled_rule_id: UUID,
    force: bool = False,
    started_by_user_id: UUID | None = None,
) -> tuple[ChangeGuard, str]:
    """Put a switched-off rule back, at its old position where that still
    means something."""
    stmt = select(UfwDisabledRule).where(
        UfwDisabledRule.id == disabled_rule_id,
        UfwDisabledRule.organization_id == organization_id,
        UfwDisabledRule.device_id == device_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise OperationError("no such disabled rule")

    if not force:
        # Re-enabling is not automatically safe: a deny returning above the
        # allow that keeps NetFleet reachable locks the host out just as a
        # move would.
        restored = _rule_from_spec(row.spec)
        position = row.position
        await _assert_change_is_safe(
            session,
            organization_id,
            device_id,
            project=lambda rules: ufw_project_inserted(rules, restored, position),
            what="Re-enabling this rule",
        )

    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    spec, position = row.spec, row.position
    guard, result = await guard_svc.run_guarded(
        session,
        organization_id,
        device_id,
        kind="ufw.rule.enable",
        started_by_user_id=started_by_user_id,
        apply=lambda creds: driver.ufw_rule_restore(
            creds, spec=spec, position=position
        ),
    )
    command, landed = result

    await session.delete(row)
    await session.commit()

    if position is not None and landed != position:
        # Drift: the ruleset moved on while this rule was switched off. The
        # rule is back, but not where it was, and ufw is first-match — so this
        # is reported rather than quietly absorbed.
        command = (
            f"{command}  [landed at position {landed}, not the "
            f"{position} it held when it was disabled]"
        )
    return guard, command


async def move_rule(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    *,
    spec: str,
    position: int,
    force: bool = False,
    started_by_user_id: UUID | None = None,
) -> tuple[ChangeGuard, str]:
    """Reorder a rule.

    The one operation where nothing is added or removed and the host can still
    become unreachable, because ufw is first-match and this changes which rule
    matches first.
    """
    status = await get_status(session, organization_id, device_id)
    target = next((r for r in status.rules if r.spec == spec), None)
    if target is None:
        raise OperationError(
            "that rule is no longer in the ruleset — reload and try again"
        )
    if target.position is None:
        # `ufw insert N` numbers the IPv4 list. A v6-only rule's position in
        # the combined table is a different number, and using it would move
        # some unrelated rule.
        raise OperationError(
            "NetFleet cannot reorder an IPv6-only rule yet — ufw numbers the "
            "two address families separately and moving by the wrong number "
            "would reorder a different rule."
        )

    if not force:
        await _assert_change_is_safe(
            session,
            organization_id,
            device_id,
            project=lambda rules: ufw_project_moved(rules, spec, position),
            what="Moving this rule",
        )

    device = await get_device(session, organization_id, device_id)
    driver = get_driver(device.vendor)
    return await guard_svc.run_guarded(
        session,
        organization_id,
        device_id,
        kind="ufw.rule.move",
        started_by_user_id=started_by_user_id,
        apply=lambda creds: driver.ufw_rule_move(creds, spec=spec, position=position),
    )
