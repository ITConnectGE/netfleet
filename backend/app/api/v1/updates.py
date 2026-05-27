"""In-app self-update endpoints — proxy to the updater container."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_admin,
)
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.updates import TriggerUpdateRequest, UpdateStatusPublic
from app.services import audit as audit_svc
from app.services import updater as updater_svc

router = APIRouter()


@router.get("/status", response_model=UpdateStatusPublic)
async def update_status(
    _: User = Depends(get_current_user),
) -> UpdateStatusPublic:
    try:
        return UpdateStatusPublic(**await updater_svc.get_status())
    except updater_svc.UpdaterUnreachable as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"updater unreachable: {e}",
        ) from e


@router.post("", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def trigger_update(
    payload: TriggerUpdateRequest,
    request: Request,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
) -> dict:
    try:
        result = await updater_svc.trigger_update(payload.version, backup=payload.backup)
    except updater_svc.UpdateInProgress as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except updater_svc.UpdaterUnreachable as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        ) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.update",
        action="trigger",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
        response_meta=result,
    )
    await session.commit()
    return result
