"""Tenant service — CRUD + ownership validation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.site import Site
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate


class TenantNotFound(Exception):
    pass


class TenantSlugTaken(Exception):
    pass


async def list_tenants(
    session: AsyncSession, organization_id: UUID
) -> list[tuple[Tenant, int, int]]:
    """Return (tenant, site_count, device_count) ordered by name."""
    sites_subq = (
        select(Site.tenant_id, func.count(Site.id).label("site_count"))
        .where(Site.organization_id == organization_id)
        .group_by(Site.tenant_id)
        .subquery()
    )
    devices_subq = (
        select(Site.tenant_id, func.count(Device.id).label("device_count"))
        .join(Device, Device.site_id == Site.id)
        .where(Site.organization_id == organization_id)
        .group_by(Site.tenant_id)
        .subquery()
    )
    stmt = (
        select(
            Tenant,
            func.coalesce(sites_subq.c.site_count, 0),
            func.coalesce(devices_subq.c.device_count, 0),
        )
        .outerjoin(sites_subq, sites_subq.c.tenant_id == Tenant.id)
        .outerjoin(devices_subq, devices_subq.c.tenant_id == Tenant.id)
        .where(Tenant.organization_id == organization_id)
        .order_by(Tenant.name)
    )
    rows = (await session.execute(stmt)).all()
    return [(t, int(sc), int(dc)) for t, sc, dc in rows]


async def get_tenant(
    session: AsyncSession, organization_id: UUID, tenant_id: UUID
) -> Tenant:
    stmt = select(Tenant).where(
        Tenant.id == tenant_id, Tenant.organization_id == organization_id
    )
    t = (await session.execute(stmt)).scalar_one_or_none()
    if t is None:
        raise TenantNotFound("tenant not found")
    return t


async def create_tenant(
    session: AsyncSession, organization_id: UUID, payload: TenantCreate
) -> Tenant:
    existing = (
        await session.execute(
            select(Tenant.id).where(
                Tenant.organization_id == organization_id, Tenant.slug == payload.slug
            )
        )
    ).first()
    if existing is not None:
        raise TenantSlugTaken(f"slug '{payload.slug}' is already in use")

    t = Tenant(organization_id=organization_id, **payload.model_dump())
    session.add(t)
    await session.flush()
    return t


async def update_tenant(
    session: AsyncSession,
    organization_id: UUID,
    tenant_id: UUID,
    payload: TenantUpdate,
) -> Tenant:
    t = await get_tenant(session, organization_id, tenant_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    await session.flush()
    return t


async def delete_tenant(
    session: AsyncSession, organization_id: UUID, tenant_id: UUID
) -> None:
    t = await get_tenant(session, organization_id, tenant_id)
    await session.delete(t)
    await session.flush()


async def assert_tenant_in_org(
    session: AsyncSession, organization_id: UUID, tenant_id: UUID
) -> None:
    if (
        await session.execute(
            select(Tenant.id).where(
                Tenant.id == tenant_id, Tenant.organization_id == organization_id
            )
        )
    ).first() is None:
        raise TenantNotFound("tenant not found in this organization")
