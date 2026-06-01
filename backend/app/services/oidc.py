"""OIDC service — per-org Microsoft Entra ID and Google Workspace.

Configuration lives on the Organization row (`microsoft_oidc_*`,
`google_oidc_*`). Earlier versions read env vars (`OIDC_*`); that path
is gone — config is managed entirely through Settings → Authorization
in the UI, which makes "swap a credential" a button click rather than
a container redeploy.

Each request builds a fresh authlib client because:
  - the same NetFleet deployment may host more than one provider
    (Microsoft + Google both enabled side-by-side);
  - secrets rotate, and a long-lived singleton would keep the old
    one cached until the next pod restart.

Construction is cheap (no network), so per-request creation is fine.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
import structlog
from authlib.integrations.starlette_client import OAuth
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_field
from app.models.organization import Organization
from app.models.user import AuthMethod, User

log = structlog.get_logger(__name__)


Provider = Literal["microsoft", "google"]
_PROVIDER_LABELS: dict[Provider, str] = {
    "microsoft": "Microsoft",
    "google": "Google",
}


class OidcDisabled(Exception):
    """Raised when an OIDC route is hit but the provider isn't enabled.
    The API layer translates this to 404 so we don't accidentally
    advertise which providers exist before a user signs in."""


class OidcError(Exception):
    """Anything else — misconfig, IdP rejection, missing claim."""


def _redirect_uri(provider: Provider) -> str:
    """Where the IdP sends the browser after consent. Must match
    exactly what the admin pasted into the IdP console — same string
    that `_auth_to_public` returns in `microsoft_redirect_uri` /
    `google_redirect_uri`."""
    base = settings.PUBLIC_URL.rstrip("/")
    return f"{base}/api/v1/auth/oidc/{provider}/callback"


def _issuer_for(provider: Provider, org: Organization) -> str:
    """Resolve the OIDC issuer URL for the configured provider."""
    if provider == "microsoft":
        tenant = (org.microsoft_oidc_tenant_id or "common").strip() or "common"
        return f"https://login.microsoftonline.com/{tenant}/v2.0"
    if provider == "google":
        return "https://accounts.google.com"
    raise OidcError(f"unknown provider: {provider}")


def _client_creds(provider: Provider, org: Organization) -> tuple[str, str]:
    """Return (client_id, client_secret) for the given provider. Raises
    OidcDisabled when the provider isn't fully configured."""
    if provider == "microsoft":
        if not org.microsoft_oidc_enabled:
            raise OidcDisabled("Microsoft sign-in is not enabled.")
        cid = (org.microsoft_oidc_client_id or "").strip()
        enc = org.microsoft_oidc_client_secret_encrypted
    else:
        if not org.google_oidc_enabled:
            raise OidcDisabled("Google sign-in is not enabled.")
        cid = (org.google_oidc_client_id or "").strip()
        enc = org.google_oidc_client_secret_encrypted
    if not cid or not enc:
        raise OidcDisabled(
            f"{_PROVIDER_LABELS[provider]} sign-in is enabled but missing "
            "client_id or client_secret."
        )
    try:
        secret = decrypt_field(enc)
    except ValueError as e:
        raise OidcError(f"cannot decrypt {provider} client secret: {e}") from e
    return cid, secret


def _build_client(provider: Provider, org: Organization) -> Any:
    """Construct a fresh authlib OAuth client for one provider."""
    cid, secret = _client_creds(provider, org)
    issuer = _issuer_for(provider, org)
    scope = "openid email profile"
    oauth = OAuth()
    # name="oidc" keeps the rest of the code base ignorant of which
    # provider we picked — callers do `oauth.oidc.authorize_redirect(...)`.
    oauth.register(
        name="oidc",
        server_metadata_url=f"{issuer.rstrip('/')}/.well-known/openid-configuration",
        client_id=cid,
        client_secret=secret,
        client_kwargs={"scope": scope},
    )
    return oauth


async def _load_org(session: AsyncSession) -> Organization:
    org = (
        await session.execute(select(Organization).limit(1))
    ).scalar_one_or_none()
    if org is None:
        raise OidcError("setup not complete — no organization exists yet")
    return org


def enabled_providers(org: Organization) -> list[dict[str, str]]:
    """Public-safe summary of which providers the admin turned on.
    Used by the login page to render the "Continue with X" buttons."""
    out: list[dict[str, str]] = []
    if org.microsoft_oidc_enabled and org.microsoft_oidc_client_id:
        out.append(
            {
                "provider": "microsoft",
                "label": "Continue with Microsoft",
                "start_url": "/api/v1/auth/oidc/microsoft/start",
            }
        )
    if org.google_oidc_enabled and org.google_oidc_client_id:
        out.append(
            {
                "provider": "google",
                "label": "Continue with Google",
                "start_url": "/api/v1/auth/oidc/google/start",
            }
        )
    return out


async def start_login(
    request: Any, session: AsyncSession, *, provider: Provider
) -> Any:
    """Return the authlib redirect that bounces the browser to the IdP
    authorize endpoint. Raises OidcDisabled when the provider isn't
    enabled (API translates to 404)."""
    org = await _load_org(session)
    oauth = _build_client(provider, org)
    return await oauth.oidc.authorize_redirect(request, _redirect_uri(provider))


async def complete_login(
    request: Any, session: AsyncSession, *, provider: Provider
) -> dict[str, Any]:
    """Exchange the authorisation code for tokens and return the
    parsed id_token claims (or userinfo as a fallback)."""
    org = await _load_org(session)
    oauth = _build_client(provider, org)
    token = await oauth.oidc.authorize_access_token(request)
    if "userinfo" in token:
        return dict(token["userinfo"])
    async with httpx.AsyncClient(timeout=15) as client:
        md = await oauth.oidc.load_server_metadata()
        r = await client.get(
            md["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {token['access_token']}"},
        )
        r.raise_for_status()
        return r.json()


async def upsert_user_from_claims(
    session: AsyncSession,
    *,
    claims: dict[str, Any],
    provider: Provider,
) -> User:
    """Find or create the user matching the OIDC subject. One org per
    deployment, so we always link to the single Organization row."""
    sub = claims.get("sub")
    email = (
        claims.get("email")
        or claims.get("preferred_username")
        or ""
    ).lower()
    name = claims.get("name") or claims.get("given_name") or email
    if not sub:
        raise OidcError("OIDC provider returned no 'sub' claim")

    # Match by oidc_sub first (the durable identity). Fall back to
    # email so an existing local account gets linked on its first SSO.
    stmt = select(User).where(User.oidc_sub == sub)
    user = (await session.execute(stmt)).scalar_one_or_none()

    provider_label = _PROVIDER_LABELS[provider]

    if user is None:
        org = await _load_org(session)
        existing = (
            await session.execute(
                select(User).where(
                    User.organization_id == org.id, User.email == email
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.oidc_sub = sub
            existing.oidc_provider = provider_label
            existing.auth_method = AuthMethod.OIDC
            user = existing
        else:
            user = User(
                organization_id=org.id,
                email=email,
                display_name=name,
                oidc_sub=sub,
                oidc_provider=provider_label,
                auth_method=AuthMethod.OIDC,
                is_active=True,
                is_admin=False,
            )
            session.add(user)
        await session.flush()
    else:
        if name and user.display_name != name:
            user.display_name = name
        if user.oidc_provider != provider_label:
            user.oidc_provider = provider_label

    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user


def random_state() -> str:
    return secrets.token_urlsafe(32)
