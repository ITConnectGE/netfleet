"""VPN endpoints — PPP secrets (L2TP/PPTP/SSTP/OVPN) for now; WireGuard lands in Phase 6c."""

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
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.secret_audit import RevealRequest
from app.schemas.vpn import (
    PppSecretCreate,
    PppSecretPasswordReset,
    PppSecretPublic,
)
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services import vpn as vpn_svc

router = APIRouter()


# ---------------- PPP secrets ----------------


@router.get("/{device_id}/ppp-secrets", response_model=list[PppSecretPublic])
async def list_ppp_secrets(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[PppSecretPublic]:
    try:
        items = await vpn_svc.list_ppp_secrets(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return [
        PppSecretPublic(
            id=s.id,
            name=s.name,
            service=s.service,
            profile=s.profile,
            local_address=s.local_address,
            remote_address=s.remote_address,
            disabled=s.disabled,
            comment=s.comment,
        )
        for s in items
    ]


@router.post(
    "/{device_id}/ppp-secrets",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def create_ppp_secret(
    device_id: UUID,
    payload: PppSecretCreate,
    request: Request,
    user: User = Depends(require_permission("ppp.secret", "write")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    try:
        new_id = await vpn_svc.add_ppp_secret(
            session,
            user.organization_id,
            device_id,
            user.id,
            name=payload.name,
            service=payload.service,
            password=payload.password,
            profile=payload.profile,
            local_address=payload.local_address,
            remote_address=payload.remote_address,
            comment=payload.comment,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ppp.secret",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude={"password"}),
        response_meta={"secret_id": new_id},
    )
    await session.commit()
    return {"id": new_id}


@router.post(
    "/{device_id}/ppp-secrets/{secret_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_ppp_secret_password(
    device_id: UUID,
    secret_id: str,
    payload: PppSecretPasswordReset,
    request: Request,
    user: User = Depends(require_permission("ppp.secret", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await vpn_svc.set_ppp_secret_password(
            session,
            user.organization_id,
            device_id,
            user.id,
            secret_id=secret_id,
            new_password=payload.new_password,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ppp.secret",
        action="reset_password",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"secret_id": secret_id},
    )
    await session.commit()


@router.delete(
    "/{device_id}/ppp-secrets/{secret_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_ppp_secret(
    device_id: UUID,
    secret_id: str,
    request: Request,
    user: User = Depends(require_permission("ppp.secret", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await vpn_svc.remove_ppp_secret(
            session,
            user.organization_id,
            device_id,
            user.id,
            secret_id=secret_id,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="ppp.secret",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"secret_id": secret_id},
    )
    await session.commit()


@router.post(
    "/{device_id}/ppp-secrets/{secret_id}/reveal",
    response_model=dict,
)
async def reveal_ppp_secret(
    device_id: UUID,
    secret_id: str,
    payload: RevealRequest,
    request: Request,
    user: User = Depends(require_permission("secret.reveal", "execute")),
    session: AsyncSession = Depends(db_session),
) -> dict:
    """Returns the plaintext password and records the reveal in the audit trail."""
    try:
        # Fetch the secret label for the audit row (best-effort).
        secrets = await vpn_svc.list_ppp_secrets(session, user.organization_id, device_id)
        label = next((f"{s.name} ({s.service})" for s in secrets if s.id == secret_id), None)

        password = await vpn_svc.reveal_ppp_secret_password(
            session,
            user.organization_id,
            device_id,
            user.id,
            secret_id=secret_id,
            secret_label=label,
            justification=payload.justification,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except vpn_svc.OperationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="secret.reveal",
        action="ppp_secret",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"secret_id": secret_id, "justification": payload.justification},
    )
    await session.commit()
    return {"password": password}
