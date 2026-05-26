"""First-run setup — creates the org + admin user when DB is empty.

This is only callable while the `organizations` table has zero rows. Once the
first org exists, /setup returns 409 and the UI redirects to /login.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import AuthMethod, User
from app.schemas.auth import SetupRequest
from app.services.rbac import seed_system_roles


class SetupAlreadyComplete(Exception):
    pass


async def setup_complete(session: AsyncSession) -> bool:
    row = (await session.execute(select(Organization.id).limit(1))).first()
    return row is not None


async def perform_setup(session: AsyncSession, payload: SetupRequest) -> tuple[Organization, User]:
    if await setup_complete(session):
        raise SetupAlreadyComplete("setup already complete")

    org = Organization(
        name=payload.organization_name,
        slug=payload.organization_slug,
        is_setup_complete=True,
    )
    session.add(org)
    await session.flush()

    admin = User(
        organization_id=org.id,
        email=payload.admin_email.lower(),
        display_name=payload.admin_display_name,
        password_hash=hash_password(payload.admin_password),
        auth_method=AuthMethod.LOCAL,
        is_admin=True,
        is_active=True,
    )
    session.add(admin)
    await session.flush()

    # Seed the built-in roles for this organization (viewer / operator).
    await seed_system_roles(session, org.id)

    return org, admin
