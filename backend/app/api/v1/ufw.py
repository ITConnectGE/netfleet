"""UFW firewall endpoints — see docs/UFW-SSH-PLAN.md.

Every write goes through `change_guard.run_guarded`; none calls the driver
directly, and none may start doing so. Read that document before adding one.
"""

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
from app.api.v1._dataclasses import fields as _fields
from app.drivers.base import UfwRuleSpec
from app.drivers.linux import _ufw_rule_from_spec as parse_ufw_spec
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.ufw import (
    ChangeGuardPublic,
    UfwDisabledRulePublic,
    UfwEnablePreflight,
    UfwRuleCreate,
    UfwRuleDelete,
    UfwRuleEdit,
    UfwRuleMove,
    UfwRulePublic,
    UfwRuleToggle,
    UfwSetEnabled,
    UfwStatusPublic,
    UfwSuggestedRule,
    UfwWriteResult,
)
from app.services import audit as audit_svc
from app.services import change_guard as guard_svc
from app.services import device as device_svc
from app.services import ufw as ufw_svc

router = APIRouter()


@router.get("/{device_id}/firewall/ufw", response_model=UfwStatusPublic)
async def get_ufw_status(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> UfwStatusPublic:
    try:
        state = await ufw_svc.get_status(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ufw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    return UfwStatusPublic(
        installed=state.installed,
        active=state.active,
        logging=state.logging,
        default_incoming=state.default_incoming,
        default_outgoing=state.default_outgoing,
        default_routed=state.default_routed,
        # `_fields`, not `vars()` — UfwRule is a slots dataclass and has no
        # __dict__. Same trap that 500'd three endpoints in 0.47.0.
        rules=[UfwRulePublic(**_fields(r)) for r in state.rules],
        app_profiles=state.app_profiles,
        rules_from_added=state.rules_from_added,
        disabled_rules=[
            _disabled_public(row)
            for row in await ufw_svc.list_disabled(
                session, user.organization_id, device_id
            )
        ],
    )


def _disabled_public(row) -> UfwDisabledRulePublic:
    """Re-parse the stored spec for display, rather than storing the display
    columns alongside it — one source of truth, and the parser is shared with
    the live rules."""
    parsed = parse_ufw_spec(row.spec)
    return UfwDisabledRulePublic(
        id=row.id,
        spec=row.spec,
        position=row.position,
        disabled_at=row.disabled_at,
        action=parsed.action,
        direction=parsed.direction,
        destination=parsed.destination,
        source=parsed.source,
        interface=parsed.interface,
        comment=parsed.comment,
    )


# ---------------- Rules ----------------
#
# Both writes route through `change_guard.run_guarded`. Neither calls the
# driver directly, and neither may start doing so.


async def _guarded_write(
    session: AsyncSession,
    user: User,
    request: Request,
    device_id: UUID,
    *,
    action: str,
    payload: dict,
    run,
) -> UfwWriteResult:
    try:
        guard, command = await run()
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ufw_svc.WouldLockOut as e:
        # 409, not 400: the request is well-formed, the host's current state is
        # what makes it unsafe.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except guard_svc.GuardUnavailable as e:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED, detail=str(e)
        ) from e
    except guard_svc.ChangeReverted as e:
        await audit_svc.write_audit(
            session,
            user_id=user.id,
            organization_id=user.organization_id,
            section="firewall.ufw",
            action=action,
            outcome=AuditOutcome.FAILED,
            device_id=device_id,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_payload=payload,
            response_meta={"restored_by_netfleet": e.restored_by_netfleet},
        )
        await session.commit()
        # 409 rather than 502: nothing is broken, the change was refused by
        # its own safety net and the host is back where it started.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.ufw",
        action=action,
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload,
        response_meta={"command": command, "guard_id": str(guard.id)},
    )
    await session.commit()
    return UfwWriteResult(
        command=command, guard=ChangeGuardPublic.model_validate(guard)
    )


@router.post(
    "/{device_id}/firewall/ufw/rules",
    response_model=UfwWriteResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_ufw_rule(
    device_id: UUID,
    payload: UfwRuleCreate,
    request: Request,
    user: User = Depends(require_permission("firewall.ufw", "write")),
    session: AsyncSession = Depends(db_session),
) -> UfwWriteResult:
    spec = UfwRuleSpec(
        action=payload.action,
        direction=payload.direction,
        from_address=payload.from_address,
        to_address=payload.to_address,
        port=payload.port,
        protocol=payload.protocol,
        interface=payload.interface,
        comment=payload.comment,
    )
    return await _guarded_write(
        session,
        user,
        request,
        device_id,
        action="rule_add",
        payload=payload.model_dump(),
        run=lambda: ufw_svc.add_rule(
            session,
            user.organization_id,
            device_id,
            spec,
            position=payload.position,
            started_by_user_id=user.id,
        ),
    )


@router.post(
    "/{device_id}/firewall/ufw/rules/delete",
    response_model=UfwWriteResult,
)
async def delete_ufw_rule(
    device_id: UUID,
    payload: UfwRuleDelete,
    request: Request,
    user: User = Depends(require_permission("firewall.ufw", "write")),
    session: AsyncSession = Depends(db_session),
) -> UfwWriteResult:
    """POST rather than DELETE: the rule is identified by its full ufw
    specification, which is a multi-word string with spaces and quotes and has
    no business in a path segment."""
    return await _guarded_write(
        session,
        user,
        request,
        device_id,
        action="rule_delete",
        payload=payload.model_dump(),
        run=lambda: ufw_svc.delete_rule(
            session,
            user.organization_id,
            device_id,
            spec=payload.spec,
            force=payload.force,
            started_by_user_id=user.id,
        ),
    )


@router.post("/{device_id}/firewall/ufw/rules/edit", response_model=UfwWriteResult)
async def edit_ufw_rule(
    device_id: UUID,
    payload: UfwRuleEdit,
    request: Request,
    user: User = Depends(require_permission("firewall.ufw", "write")),
    session: AsyncSession = Depends(db_session),
) -> UfwWriteResult:
    """Replace a rule. The replacement is inserted before the original is
    removed, so there is never a moment with neither in place."""
    spec = UfwRuleSpec(
        action=payload.action,
        direction=payload.direction,
        from_address=payload.from_address,
        to_address=payload.to_address,
        port=payload.port,
        protocol=payload.protocol,
        interface=payload.interface,
        comment=payload.comment,
    )
    return await _guarded_write(
        session,
        user,
        request,
        device_id,
        action="rule_edit",
        payload=payload.model_dump(),
        run=lambda: ufw_svc.edit_rule(
            session,
            user.organization_id,
            device_id,
            old_spec=payload.spec,
            spec=spec,
            position=payload.position,
            force=payload.force,
            started_by_user_id=user.id,
        ),
    )


@router.post("/{device_id}/firewall/ufw/rules/move", response_model=UfwWriteResult)
async def move_ufw_rule(
    device_id: UUID,
    payload: UfwRuleMove,
    request: Request,
    user: User = Depends(require_permission("firewall.ufw", "write")),
    session: AsyncSession = Depends(db_session),
) -> UfwWriteResult:
    return await _guarded_write(
        session,
        user,
        request,
        device_id,
        action="rule_move",
        payload=payload.model_dump(),
        run=lambda: ufw_svc.move_rule(
            session,
            user.organization_id,
            device_id,
            spec=payload.spec,
            position=payload.position,
            force=payload.force,
            started_by_user_id=user.id,
        ),
    )


@router.post("/{device_id}/firewall/ufw/rules/disable", response_model=UfwWriteResult)
async def disable_ufw_rule(
    device_id: UUID,
    payload: UfwRuleToggle,
    request: Request,
    user: User = Depends(require_permission("firewall.ufw", "write")),
    session: AsyncSession = Depends(db_session),
) -> UfwWriteResult:
    """Switch a rule off.

    ufw has no disabled state, so the rule is removed from the host and
    remembered in NetFleet. It will not appear in `ufw status` on the host
    while it is off.
    """
    return await _guarded_write(
        session,
        user,
        request,
        device_id,
        action="rule_disable",
        payload=payload.model_dump(),
        run=lambda: ufw_svc.disable_rule(
            session,
            user.organization_id,
            device_id,
            spec=payload.spec,
            force=payload.force,
            started_by_user_id=user.id,
        ),
    )


@router.post(
    "/{device_id}/firewall/ufw/disabled/{disabled_rule_id}/enable",
    response_model=UfwWriteResult,
)
async def enable_ufw_rule(
    device_id: UUID,
    disabled_rule_id: UUID,
    request: Request,
    force: bool = False,
    user: User = Depends(require_permission("firewall.ufw", "write")),
    session: AsyncSession = Depends(db_session),
) -> UfwWriteResult:
    """Put a switched-off rule back, at its old position where that is still
    a position that exists."""
    return await _guarded_write(
        session,
        user,
        request,
        device_id,
        action="rule_enable",
        payload={"disabled_rule_id": str(disabled_rule_id), "force": force},
        run=lambda: ufw_svc.enable_rule(
            session,
            user.organization_id,
            device_id,
            disabled_rule_id=disabled_rule_id,
            force=force,
            started_by_user_id=user.id,
        ),
    )


# ---------------- The firewall itself ----------------


@router.get(
    "/{device_id}/firewall/ufw/enable-preflight",
    response_model=UfwEnablePreflight,
)
async def get_enable_preflight(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> UfwEnablePreflight:
    """Everything the enable dialog needs to be specific rather than generic.

    Read-only — this changes nothing on the host.
    """
    try:
        pre = await ufw_svc.enable_preflight(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ufw_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    return UfwEnablePreflight(
        already_active=pre.already_active,
        management_address=pre.management_address,
        management_port=pre.management_port,
        default_incoming=pre.default_incoming,
        covered=pre.covered,
        covering_rule_spec=pre.covering_rule_spec,
        covering_rule_summary=pre.covering_rule_summary,
        suggested_rule=(
            UfwSuggestedRule(**_fields(pre.suggested_rule, drop={"to_address", "interface"}))
            if pre.suggested_rule
            else None
        ),
    )


@router.post("/{device_id}/firewall/ufw/enabled", response_model=UfwWriteResult)
async def set_ufw_enabled(
    device_id: UUID,
    payload: UfwSetEnabled,
    request: Request,
    user: User = Depends(require_permission("firewall.ufw", "execute")),
    session: AsyncSession = Depends(db_session),
) -> UfwWriteResult:
    """Switch the whole firewall on or off.

    `execute` rather than `write`: this is a bigger hammer than editing a rule
    and worth being able to grant separately.
    """
    return await _guarded_write(
        session,
        user,
        request,
        device_id,
        # Audited distinctly so a forced enable is findable in the log without
        # reading payloads.
        action=(
            "enable_forced"
            if payload.enabled and payload.force and not payload.allow_management
            else "enable"
            if payload.enabled
            else "disable"
        ),
        payload=payload.model_dump(),
        run=lambda: ufw_svc.set_enabled(
            session,
            user.organization_id,
            device_id,
            enabled=payload.enabled,
            allow_management=payload.allow_management,
            force=payload.force,
            started_by_user_id=user.id,
        ),
    )


# ---------------- Change guards ----------------
#
# A guard is armed automatically by any guarded write and disarmed the moment
# the change verifies. These endpoints exist for the case that verification
# could not settle: the operator can see the host is fine and confirm, or
# decide it is not and roll back without waiting out the window.


@router.get("/{device_id}/firewall/guards", response_model=list[ChangeGuardPublic])
async def list_pending_guards(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[ChangeGuardPublic]:
    guards = await guard_svc.list_pending(session, user.organization_id, device_id)
    return [ChangeGuardPublic.model_validate(g) for g in guards]


async def _resolve_guard(
    session: AsyncSession,
    user: User,
    request: Request,
    device_id: UUID,
    guard_id: UUID,
    *,
    action: str,
) -> ChangeGuardPublic:
    fn = guard_svc.confirm if action == "confirm" else guard_svc.rollback
    try:
        guard = await fn(session, user.organization_id, guard_id)
    except guard_svc.GuardNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except guard_svc.GuardNotArmed as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="firewall.ufw",
        action=f"guard_{action}",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"guard_id": str(guard_id)},
    )
    await session.commit()
    return ChangeGuardPublic.model_validate(guard)


@router.post(
    "/{device_id}/firewall/guards/{guard_id}/confirm",
    response_model=ChangeGuardPublic,
)
async def confirm_guard(
    device_id: UUID,
    guard_id: UUID,
    request: Request,
    user: User = Depends(require_permission("firewall.ufw", "write")),
    session: AsyncSession = Depends(db_session),
) -> ChangeGuardPublic:
    """Keep the change: cancel the host's pending rollback."""
    return await _resolve_guard(
        session, user, request, device_id, guard_id, action="confirm"
    )


@router.post(
    "/{device_id}/firewall/guards/{guard_id}/rollback",
    response_model=ChangeGuardPublic,
)
async def rollback_guard(
    device_id: UUID,
    guard_id: UUID,
    request: Request,
    user: User = Depends(require_permission("firewall.ufw", "write")),
    session: AsyncSession = Depends(db_session),
) -> ChangeGuardPublic:
    """Undo the change now rather than waiting for the window to elapse."""
    return await _resolve_guard(
        session, user, request, device_id, guard_id, action="rollback"
    )
