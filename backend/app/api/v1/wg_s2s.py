"""Site-to-site WireGuard wizard endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, require_permission
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.wg_s2s import S2SCreateRequest, S2SCreateResponse
from app.services import audit as audit_svc
from app.services import wg_s2s as wg_s2s_svc

router = APIRouter()


@router.post(
    "",
    response_model=S2SCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_site_to_site(
    payload: S2SCreateRequest,
    request: Request,
    user: User = Depends(require_permission("vpn.wireguard.peer", "write")),
    session: AsyncSession = Depends(db_session),
) -> S2SCreateResponse:
    try:
        out = await wg_s2s_svc.create_site_to_site(
            session, user.organization_id, payload
        )
    except wg_s2s_svc.S2SError as e:
        # Surface what we managed to provision so the operator can
        # clean up manually instead of being stuck guessing.
        await audit_svc.write_audit(
            session,
            user_id=user.id,
            organization_id=user.organization_id,
            section="vpn.wireguard.peer",
            action="site_to_site_partial",
            outcome=AuditOutcome.FAILED,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_payload=payload.model_dump(mode="json"),
            response_meta={
                "error": str(e),
                "artifacts": [a.model_dump() for a in e.artifacts],
            },
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": str(e),
                "artifacts": [a.model_dump() for a in e.artifacts],
                "public_key_a": e.public_key_a,
                "public_key_b": e.public_key_b,
            },
        ) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="vpn.wireguard.peer",
        action="site_to_site_create",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(mode="json"),
        response_meta={
            "comment_tag": out.comment_tag,
            "artifact_count": len(out.artifacts),
        },
    )
    await session.commit()
    return out
