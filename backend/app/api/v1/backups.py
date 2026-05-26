"""Device backup endpoints: list history, trigger manual backup, download files."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.models.audit_log import AuditOutcome
from app.models.device_backup import BackupSource
from app.models.user import User
from app.schemas.backups import DeviceBackupPublic
from app.services import audit as audit_svc
from app.services import backups as backup_svc
from app.services import device as device_svc

router = APIRouter()


def _to_public(row) -> DeviceBackupPublic:
    return DeviceBackupPublic(
        id=row.id,
        ts=row.ts,
        device_id=row.device_id,
        triggered_by_user_id=row.triggered_by_user_id,
        source=row.source,
        status=row.status,
        backup_filename=row.backup_filename,
        rsc_filename=row.rsc_filename,
        backup_size_bytes=row.backup_size_bytes,
        rsc_size_bytes=row.rsc_size_bytes,
        error_message=row.error_message,
        duration_ms=row.duration_ms,
    )


@router.get("/{device_id}/backups", response_model=list[DeviceBackupPublic])
async def list_device_backups(
    device_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[DeviceBackupPublic]:
    rows = await backup_svc.list_history(
        session, user.organization_id, device_id=device_id, limit=limit
    )
    return [_to_public(r) for r in rows]


@router.post(
    "/{device_id}/backups",
    response_model=DeviceBackupPublic,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_manual_backup(
    device_id: UUID,
    request: Request,
    user: User = Depends(require_permission("system.backup", "execute")),
    session: AsyncSession = Depends(db_session),
) -> DeviceBackupPublic:
    try:
        row = await backup_svc.run_backup(
            session,
            organization_id=user.organization_id,
            device_id=device_id,
            triggered_by_user_id=user.id,
            source=BackupSource.MANUAL,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.backup",
        action="manual",
        outcome=AuditOutcome.OK if row.status.value == "ok" else AuditOutcome.FAILED,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        response_meta={"backup_id": str(row.id), "duration_ms": row.duration_ms},
        error_message=row.error_message,
    )
    await session.commit()
    return _to_public(row)


@router.get(
    "/{device_id}/backups/{backup_id}/file/{kind}",
    response_class=FileResponse,
)
async def download_backup_file(
    device_id: UUID,
    backup_id: UUID,
    kind: str,
    request: Request,
    user: User = Depends(require_permission("system.backup", "read")),
    session: AsyncSession = Depends(db_session),
):
    """kind = 'backup' (binary RouterOS .backup) | 'rsc' (text /export script)."""
    if kind not in ("backup", "rsc"):
        raise HTTPException(status_code=400, detail="kind must be 'backup' or 'rsc'")

    rows = await backup_svc.list_history(session, user.organization_id, device_id=device_id, limit=500)
    row = next((r for r in rows if r.id == backup_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="backup not found")

    filename = row.backup_filename if kind == "backup" else row.rsc_filename
    if not filename:
        raise HTTPException(status_code=404, detail=f"no {kind} file for this backup")

    try:
        path = backup_svc.backup_file_path(device_id, filename)
    except backup_svc.BackupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.backup",
        action="download",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"backup_id": str(backup_id), "kind": kind, "filename": filename},
    )
    await session.commit()

    media = "application/octet-stream" if kind == "backup" else "text/plain"
    return FileResponse(path, filename=filename, media_type=media)
