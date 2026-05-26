"""Site service — CRUD plus per-org isolation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.site import Site
from app.schemas.site import SiteCreate, SiteUpdate


class SiteNotFound(Exception):
    pass


class SiteSlugTaken(Exception):
    pass


async def list_sites(session: AsyncSession, organization_id: UUID) -> list[tuple[Site, int]]:
    """Return (site, device_count) tuples ordered by name."""
    stmt = (
        select(Site, func.count(Device.id))
        .outerjoin(Device, Device.site_id == Site.id)
        .where(Site.organization_id == organization_id)
        .group_by(Site.id)
        .order_by(Site.name)
    )
    result = await session.execute(stmt)
    return [(s, int(c or 0)) for s, c in result.all()]


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
    # Slug uniqueness within org
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
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(site, k, v)
    await session.flush()
    return site


async def delete_site(session: AsyncSession, organization_id: UUID, site_id: UUID) -> None:
    site = await get_site(session, organization_id, site_id)
    await session.delete(site)
    await session.flush()
