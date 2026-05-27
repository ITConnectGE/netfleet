"""Tenants endpoints — CRUD + audit logging."""

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
from app.schemas.tenant import TenantCreate, TenantPublic, TenantUpdate
from app.services import audit as audit_svc
from app.services import tenant as tenant_svc

router = APIRouter()


def _to_public(t, site_count: int = 0, device_count: int = 0) -> TenantPublic:
    return TenantPublic.model_validate(
        {**t.__dict__, "site_count": site_count, "device_count": device_count}
    )


@router.get("", response_model=list[TenantPublic])
async def list_tenants(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[TenantPublic]:
    items = await tenant_svc.list_tenants(session, user.organization_id)
    return [_to_public(t, sc, dc) for t, sc, dc in items]


@router.post("", response_model=TenantPublic, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    request: Request,
    user: User = Depends(require_permission("tenants", "write")),
    session: AsyncSession = Depends(db_session),
) -> TenantPublic:
    try:
        t = await tenant_svc.create_tenant(session, user.organization_id, payload)
    except tenant_svc.TenantSlugTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="tenants",
        action="create",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
    )
    await session.commit()
    return _to_public(t)


@router.get("/{tenant_id}", response_model=TenantPublic)
async def get_tenant(
    tenant_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> TenantPublic:
    try:
        t = await tenant_svc.get_tenant(session, user.organization_id, tenant_id)
    except tenant_svc.TenantNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _to_public(t)


@router.patch("/{tenant_id}", response_model=TenantPublic)
async def update_tenant(
    tenant_id: UUID,
    payload: TenantUpdate,
    request: Request,
    user: User = Depends(require_permission("tenants", "write")),
    session: AsyncSession = Depends(db_session),
) -> TenantPublic:
    try:
        t = await tenant_svc.update_tenant(session, user.organization_id, tenant_id, payload)
    except tenant_svc.TenantNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="tenants",
        action="update",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return _to_public(t)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: UUID,
    request: Request,
    user: User = Depends(require_permission("tenants", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await tenant_svc.delete_tenant(session, user.organization_id, tenant_id)
    except tenant_svc.TenantNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="tenants",
        action="delete",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
