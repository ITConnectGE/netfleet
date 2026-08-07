"""UFW firewall endpoints.

Reads plus the change-guard controls (F1 and F2 of docs/UFW-SSH-PLAN.md).
Every rule write added later must go through `change_guard.run_guarded` —
read that document before adding one here.
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
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.ufw import (
    ChangeGuardPublic,
    UfwRuleCreate,
    UfwRuleDelete,
    UfwRulePublic,
    UfwStatusPublic,
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
