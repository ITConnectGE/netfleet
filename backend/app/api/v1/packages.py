"""Package management endpoints.

Reads are synchronous. Refresh and upgrade are not: `apt-get upgrade` on a
neglected host runs for tens of minutes, so those record a run, start a
background task and return the row to poll.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.api.v1._dataclasses import fields as _fields
from app.drivers.base import UnsupportedOperation
from app.models.audit_log import AuditOutcome
from app.models.package_run import PackageRunKind
from app.models.user import User
from app.schemas.packages import (
    PackageRunPublic,
    PackageStatePublic,
    PackageUpdatePublic,
    PackageUpgradeRequest,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services import packages as pkg_svc
from app.services.device import HostKeyNotPinned

router = APIRouter()


@router.get("/{device_id}/packages", response_model=PackageStatePublic)
async def get_packages(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> PackageStatePublic:
    try:
        state = await pkg_svc.get_state(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except (UnsupportedOperation, HostKeyNotPinned):
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    return PackageStatePublic(
        manager=state.manager,
        # `_fields`, not `vars()` — PackageUpdate is a slots dataclass and
        # has no __dict__. Same trap that 500'd three endpoints in 0.47.0.
        updates=[PackageUpdatePublic(**_fields(u)) for u in state.updates],
        security_count=state.security_count,
        reboot_required=state.reboot_required,
        reboot_required_by=state.reboot_required_by,
        last_refreshed_iso=state.last_refreshed_iso,
    )


@router.get("/{device_id}/package-runs", response_model=list[PackageRunPublic])
async def list_package_runs(
    device_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[PackageRunPublic]:
    runs = await pkg_svc.list_runs(
        session, user.organization_id, device_id, limit=limit
    )
    return [PackageRunPublic.model_validate(r) for r in runs]


async def _start(
    session: AsyncSession,
    user: User,
    request: Request,
    device_id: UUID,
    kind: PackageRunKind,
    *,
    packages: list[str] | None = None,
    security_only: bool = False,
) -> PackageRunPublic:
    try:
        run = await pkg_svc.start_run(
            session,
            user.organization_id,
            device_id,
            kind=kind,
            packages=packages,
            security_only=security_only,
            started_by_user_id=user.id,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except pkg_svc.PackageRunInProgress as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except (UnsupportedOperation, HostKeyNotPinned):
        raise

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="pkg.manager",
        action=kind.value,
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"packages": packages or [], "security_only": security_only},
    )
    await session.commit()
    return PackageRunPublic.model_validate(run)


@router.post(
    "/{device_id}/packages/refresh",
    response_model=PackageRunPublic,
    status_code=status.HTTP_202_ACCEPTED,
)
async def refresh_packages(
    device_id: UUID,
    request: Request,
    user: User = Depends(require_permission("pkg.manager", "write")),
    session: AsyncSession = Depends(db_session),
) -> PackageRunPublic:
    return await _start(session, user, request, device_id, PackageRunKind.REFRESH)


@router.post(
    "/{device_id}/packages/upgrade",
    response_model=PackageRunPublic,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upgrade_packages(
    device_id: UUID,
    payload: PackageUpgradeRequest,
    request: Request,
    user: User = Depends(require_permission("pkg.manager", "execute")),
    session: AsyncSession = Depends(db_session),
) -> PackageRunPublic:
    """Upgrade packages. Returns 202 with a run to poll — the work itself
    outlives this request by minutes."""
    return await _start(
        session,
        user,
        request,
        device_id,
        PackageRunKind.UPGRADE,
        packages=payload.packages or None,
        security_only=payload.security_only,
    )


@router.post("/packages/refresh-all", status_code=status.HTTP_202_ACCEPTED)
async def refresh_all_package_counts(
    request: Request,
    user: User = Depends(require_permission("pkg.manager", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict[str, int]:
    """Re-read pending updates for every enabled server in the org.

    Sequential inside the service, so this can take a while on a large
    fleet — but it is the same work the nightly sweep does, just on
    demand.
    """
    ok, failed = await pkg_svc.refresh_fleet_packages(session, user.organization_id)
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="pkg.manager",
        action="refresh_all",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        response_meta={"ok": ok, "failed": failed},
    )
    await session.commit()
    return {"checked": ok, "failed": failed}
