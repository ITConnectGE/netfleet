"""Bulk operations endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, require_permission
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.device_ops import BulkPasswordResetRequest, BulkPasswordResetResponse
from app.services import audit as audit_svc
from app.services import bulk as bulk_svc

router = APIRouter()


@router.post(
    "/device-users/password-reset",
    response_model=BulkPasswordResetResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_device_user_password_reset(
    payload: BulkPasswordResetRequest,
    request: Request,
    user: User = Depends(require_permission("system.user", "write")),
    session: AsyncSession = Depends(db_session),
) -> BulkPasswordResetResponse:
    results = await bulk_svc.bulk_password_reset(
        session,
        user.organization_id,
        device_ids=payload.device_ids,
        username=payload.username,
        new_password=payload.new_password,
    )

    succeeded = sum(1 for r in results if r.status == "ok")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")

    # Single audit row for the whole bulk operation
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="system.user",
        action="bulk_reset_password",
        outcome=AuditOutcome.OK if failed == 0 else AuditOutcome.FAILED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "target_username": payload.username,
            "device_count": len(payload.device_ids),
        },
        response_meta={
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        },
    )
    await session.commit()

    return BulkPasswordResetResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        results=results,
    )
