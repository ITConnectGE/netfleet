"""Sites endpoints — CRUD + audit logging."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, get_current_user, require_permission
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.site import SiteCreate, SitePublic, SiteUpdate
from app.services import audit as audit_svc
from app.services import site as site_svc
from app.services import tenant as tenant_svc

router = APIRouter()


def _to_public(site, tenant_name: str | None = None, device_count: int = 0) -> SitePublic:
    return SitePublic.model_validate(
        {**site.__dict__, "tenant_name": tenant_name, "device_count": device_count}
    )


@router.get("", response_model=list[SitePublic])
async def list_sites(
    tenant_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[SitePublic]:
    items = await site_svc.list_sites(session, user.organization_id, tenant_id=tenant_id)
    return [_to_public(s, tname, c) for s, tname, c in items]


@router.post("", response_model=SitePublic, status_code=status.HTTP_201_CREATED)
async def create_site(
    payload: SiteCreate,
    request: Request,
    user: User = Depends(require_permission("sites", "write")),
    session: AsyncSession = Depends(db_session),
) -> SitePublic:
    try:
        site = await site_svc.create_site(session, user.organization_id, payload)
    except site_svc.SiteSlugTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except tenant_svc.TenantNotFound as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="sites",
        action="create",
        outcome=AuditOutcome.OK,
        site_id=site.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
    )
    await session.commit()
    return _to_public(site, None, 0)


@router.get("/{site_id}", response_model=SitePublic)
async def get_site(
    site_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> SitePublic:
    try:
        site = await site_svc.get_site(session, user.organization_id, site_id)
    except site_svc.SiteNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _to_public(site)


@router.patch("/{site_id}", response_model=SitePublic)
async def update_site(
    site_id: UUID,
    payload: SiteUpdate,
    request: Request,
    user: User = Depends(require_permission("sites", "write")),
    session: AsyncSession = Depends(db_session),
) -> SitePublic:
    try:
        site = await site_svc.update_site(session, user.organization_id, site_id, payload)
    except site_svc.SiteNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="sites",
        action="update",
        outcome=AuditOutcome.OK,
        site_id=site.id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return _to_public(site)


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: UUID,
    request: Request,
    user: User = Depends(require_permission("sites", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await site_svc.delete_site(session, user.organization_id, site_id)
    except site_svc.SiteNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="sites",
        action="delete",
        outcome=AuditOutcome.OK,
        site_id=site_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
