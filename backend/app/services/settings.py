"""Organization-scoped settings service — currently just SMTP."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_field
from app.models.organization import Organization
from app.schemas.settings import SmtpSettingsUpdate


class OrganizationNotFound(Exception):
    pass


async def get_organization(session: AsyncSession, organization_id: UUID) -> Organization:
    org = (
        await session.execute(select(Organization).where(Organization.id == organization_id))
    ).scalar_one_or_none()
    if org is None:
        raise OrganizationNotFound("organization not found")
    return org


async def update_org_info(
    session: AsyncSession,
    organization_id: UUID,
    *,
    netfleet_external_ips: str | None = None,
) -> Organization:
    org = await get_organization(session, organization_id)
    # Treat empty string as "clear" so the UI can unset it.
    if netfleet_external_ips is not None:
        org.netfleet_external_ips = netfleet_external_ips or None
    await session.flush()
    return org


async def update_smtp(
    session: AsyncSession,
    organization_id: UUID,
    payload: SmtpSettingsUpdate,
) -> Organization:
    org = await get_organization(session, organization_id)
    data = payload.model_dump(exclude_unset=True)

    # Password handling: empty string clears, non-empty encrypts, missing leaves untouched.
    if "smtp_password" in data:
        raw = data.pop("smtp_password")
        org.smtp_password_encrypted = encrypt_field(raw) if raw else None

    for key, value in data.items():
        setattr(org, key, value)

    await session.flush()
    return org
