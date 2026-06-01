"""Organization-scoped settings service — SMTP, SMS, authorization."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_field
from app.models.organization import Organization
from app.schemas.settings import AuthSettingsUpdate, SmtpSettingsUpdate


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


async def update_auth(
    session: AsyncSession,
    organization_id: UUID,
    payload: AuthSettingsUpdate,
) -> Organization:
    """Update OIDC + MFA toggles. Client secrets are encrypted at rest."""
    org = await get_organization(session, organization_id)
    data = payload.model_dump(exclude_unset=True)

    # Client secrets: same trichotomy as SMTP password.
    for raw_key, enc_attr in (
        ("microsoft_oidc_client_secret", "microsoft_oidc_client_secret_encrypted"),
        ("google_oidc_client_secret", "google_oidc_client_secret_encrypted"),
    ):
        if raw_key in data:
            raw = data.pop(raw_key)
            setattr(org, enc_attr, encrypt_field(raw) if raw else None)

    # Treat empty strings as "clear" on optional text fields.
    nullable_text = (
        "microsoft_oidc_tenant_id",
        "microsoft_oidc_client_id",
        "google_oidc_client_id",
    )
    for k, v in data.items():
        if k in nullable_text and isinstance(v, str) and not v.strip():
            v = None
        setattr(org, k, v)

    await session.flush()
    return org
