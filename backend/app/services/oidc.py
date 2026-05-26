"""OIDC (Microsoft Entra ID, Authentik, Keycloak, Google…) — generic provider."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.organization import Organization
from app.models.user import AuthMethod, User

log = structlog.get_logger(__name__)


class OidcDisabled(Exception):
    """Raised when an OIDC route is called but OIDC is not configured."""


class OidcError(Exception):
    """Raised for any other OIDC error."""


_oauth: OAuth | None = None


def _client() -> OAuth:
    global _oauth
    if _oauth is None:
        if not settings.OIDC_ENABLED:
            raise OidcDisabled("OIDC not enabled")
        if not (settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID and settings.OIDC_CLIENT_SECRET):
            raise OidcDisabled("OIDC misconfigured (missing issuer/client_id/client_secret)")
        oauth = OAuth()
        oauth.register(
            name="oidc",
            server_metadata_url=f"{settings.OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration",
            client_id=settings.OIDC_CLIENT_ID,
            client_secret=settings.OIDC_CLIENT_SECRET,
            client_kwargs={"scope": settings.OIDC_SCOPES},
        )
        _oauth = oauth
    return _oauth


async def start_login(request: Any) -> Any:
    """Returns an authlib RedirectResponse to the IdP."""
    return await _client().oidc.authorize_redirect(request, settings.OIDC_REDIRECT_URI)


async def complete_login(request: Any) -> dict[str, Any]:
    """Exchange the code for tokens and return the parsed id_token claims."""
    token = await _client().oidc.authorize_access_token(request)
    if "userinfo" in token:
        claims = dict(token["userinfo"])
    else:
        # Fallback: hit the userinfo endpoint directly
        async with httpx.AsyncClient(timeout=15) as client:
            md = await _client().oidc.load_server_metadata()
            r = await client.get(
                md["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {token['access_token']}"},
            )
            r.raise_for_status()
            claims = r.json()
    return claims


async def upsert_user_from_claims(
    session: AsyncSession,
    *,
    claims: dict[str, Any],
) -> User:
    """Find or create the user matching the OIDC subject. One org per deployment."""
    sub = claims.get("sub")
    email = claims.get("email") or claims.get("preferred_username") or ""
    name = claims.get("name") or claims.get("given_name") or email
    if not sub:
        raise OidcError("OIDC provider returned no 'sub' claim")

    stmt = select(User).where(User.oidc_sub == sub)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is None:
        org = (await session.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org is None:
            raise OidcError("setup not complete — no organization exists yet")
        # Optional: match by email to an existing local user and link
        existing = (
            await session.execute(
                select(User).where(User.organization_id == org.id, User.email == email.lower())
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.oidc_sub = sub
            existing.oidc_provider = settings.OIDC_PROVIDER_NAME
            existing.auth_method = AuthMethod.OIDC
            user = existing
        else:
            user = User(
                organization_id=org.id,
                email=email.lower(),
                display_name=name,
                oidc_sub=sub,
                oidc_provider=settings.OIDC_PROVIDER_NAME,
                auth_method=AuthMethod.OIDC,
                is_active=True,
                is_admin=False,
            )
            session.add(user)
        await session.flush()
    else:
        # Refresh display name if it changed upstream
        if name and user.display_name != name:
            user.display_name = name

    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user


def random_state() -> str:
    return secrets.token_urlsafe(32)
