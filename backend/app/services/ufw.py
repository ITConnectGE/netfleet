"""UFW service.

Every write here goes through `change_guard.run_guarded`. None of them may
call the driver directly — see docs/UFW-SSH-PLAN.md before adding one.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.drivers.base import UfwRuleSpec, UfwStatus, UnsupportedOperation
from app.drivers.linux import ufw_rule_covers_path
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


async def _assert_delete_is_safe(
    session: AsyncSession,
    organization_id: UUID,
    device_id: UUID,
    spec: str,
) -> None:
    """Refuse a delete that would remove the last rule holding the door open.

    The guard would catch the lockout and undo it, but only after the host has
    spent up to two minutes unreachable. Refusing up front is cheaper, and the
    message can name what would break.
    """
    path = await guard_svc.management_path(session, organization_id, device_id)
    if not path.known:
        # Nothing to reason about. The guard remains the backstop.
        return

    status = await get_status(session, organization_id, device_id)
    if not status.active:
        # Nothing is being enforced, so nothing can be cut by removing a rule.
        return

    covering = [r for r in status.rules if ufw_rule_covers_path(r, path)]
    target = next((r for r in status.rules if r.spec == spec), None)
    if target is None or not ufw_rule_covers_path(target, path):
        return
    if len(covering) > 1:
        return

    raise WouldLockOut(
        f"This is the only rule allowing NetFleet to reach this host "
        f"({path.client_address} → port {path.server_port}). Deleting it would "
        "make the host unmanageable. Add a replacement rule first, or repeat "
        "the request with force if you have another way in."
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
        await _assert_delete_is_safe(session, organization_id, device_id, spec)

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
