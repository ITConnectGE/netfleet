"""UFW service.

Every write here goes through `change_guard.run_guarded`. None of them may
call the driver directly — see docs/UFW-SSH-PLAN.md before adding one.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.drivers.base import UfwRule, UfwRuleSpec, UfwStatus, UnsupportedOperation
from app.drivers.linux import ufw_would_lock_out
from app.models.change_guard import ChangeGuard
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
            project=lambda rules: [r for r in rules if r.spec != spec],
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


def _as_rule(spec: UfwRuleSpec) -> UfwRule:
    """The projected shape of a rule that does not exist yet.

    Only the fields the safety check reads are filled — this never leaves the
    simulation, so inventing a position or an ip_version would be noise.
    """
    destination = spec.port or "Anywhere"
    if spec.port and spec.protocol:
        destination = f"{spec.port}/{spec.protocol}"
    return UfwRule(
        action=spec.action,
        direction=spec.direction,
        destination=destination,
        source=spec.from_address or "Anywhere",
        interface=spec.interface,
        comment=spec.comment,
    )


def _replaced(rules: list[UfwRule], old_spec: str, new: UfwRule, position: int | None):
    """The ruleset after an edit, in the order it would end up in."""
    remaining = [r for r in rules if r.spec != old_spec]
    if position is None:
        # ufw appends when no position is given.
        original = next((i for i, r in enumerate(rules) if r.spec == old_spec), None)
        index = len(remaining) if original is None else original
    else:
        index = min(max(position - 1, 0), len(remaining))
    return remaining[:index] + [new] + remaining[index:]


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
            project=lambda rules: _replaced(
                rules, old_spec, _as_rule(spec), position
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


def _moved(rules: list[UfwRule], spec: str, position: int) -> list[UfwRule]:
    target = next((r for r in rules if r.spec == spec), None)
    if target is None:
        return rules
    remaining = [r for r in rules if r.spec != spec]
    index = min(max(position - 1, 0), len(remaining))
    return remaining[:index] + [target] + remaining[index:]


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
            project=lambda rules: _moved(rules, spec, position),
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
