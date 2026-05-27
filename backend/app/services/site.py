"""Site service — CRUD plus per-org isolation + tenant validation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.site import Site
from app.models.tenant import Tenant
from app.schemas.site import SiteCreate, SiteUpdate
from app.services import tenant as tenant_svc


class SiteNotFound(Exception):
    pass


class SiteSlugTaken(Exception):
    pass


async def list_sites(
    session: AsyncSession,
    organization_id: UUID,
    *,
    tenant_id: UUID | None = None,
) -> list[tuple[Site, str | None, int]]:
    """Return (site, tenant_name, device_count) tuples ordered by tenant then name."""
    stmt = (
        select(Site, Tenant.name, func.count(Device.id))
        .join(Tenant, Tenant.id == Site.tenant_id)
        .outerjoin(Device, Device.site_id == Site.id)
        .where(Site.organization_id == organization_id)
        .group_by(Site.id, Tenant.name)
        .order_by(Tenant.name, Site.name)
    )
    if tenant_id is not None:
        stmt = stmt.where(Site.tenant_id == tenant_id)
    result = await session.execute(stmt)
    return [(s, tname, int(c or 0)) for s, tname, c in result.all()]


async def get_site(session: AsyncSession, organization_id: UUID, site_id: UUID) -> Site:
    stmt = select(Site).where(Site.id == site_id, Site.organization_id == organization_id)
    site = (await session.execute(stmt)).scalar_one_or_none()
    if site is None:
        raise SiteNotFound("site not found")
    return site


async def create_site(
    session: AsyncSession,
    organization_id: UUID,
    payload: SiteCreate,
) -> Site:
    # Validate tenant belongs to this org
    await tenant_svc.assert_tenant_in_org(session, organization_id, payload.tenant_id)

    # Slug uniqueness within org (sites are unique across tenants within an org)
    existing = (
        await session.execute(
            select(Site.id).where(
                Site.organization_id == organization_id, Site.slug == payload.slug
            )
        )
    ).first()
    if existing is not None:
        raise SiteSlugTaken(f"slug '{payload.slug}' is already in use")

    site = Site(organization_id=organization_id, **payload.model_dump())
    session.add(site)
    await session.flush()
    return site


async def update_site(
    session: AsyncSession,
    organization_id: UUID,
    site_id: UUID,
    payload: SiteUpdate,
) -> Site:
    site = await get_site(session, organization_id, site_id)
    data = payload.model_dump(exclude_unset=True)
    if "tenant_id" in data and data["tenant_id"] is not None:
        await tenant_svc.assert_tenant_in_org(session, organization_id, data["tenant_id"])
    for k, v in data.items():
        setattr(site, k, v)
    await session.flush()
    return site


async def delete_site(session: AsyncSession, organization_id: UUID, site_id: UUID) -> None:
    site = await get_site(session, organization_id, site_id)
    await session.delete(site)
    await session.flush()
