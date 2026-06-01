"""OIDC endpoints — Microsoft Entra ID and Google Workspace.

Provider config now lives on the Organization row (managed from
Settings → Authorization), so unlike the env-driven implementation the
admin can flip providers on/off without a redeploy.

Per-provider URLs (preferred):
  GET /api/v1/auth/oidc/microsoft/start
  GET /api/v1/auth/oidc/microsoft/callback
  GET /api/v1/auth/oidc/google/start
  GET /api/v1/auth/oidc/google/callback

Legacy auto-dispatch (back-compat — bookmarked links, old IdP entries):
  GET /api/v1/auth/oidc/start      → falls back to whichever provider
  GET /api/v1/auth/oidc/callback     is enabled (Microsoft first, then
                                     Google). 404 when neither is on.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session
from app.api.v1.auth import _set_refresh_cookie
from app.core.config import settings
from app.services import auth as auth_svc
from app.services import oidc as oidc_svc

router = APIRouter()


Provider = Literal["microsoft", "google"]


async def _resolve_legacy_provider(session: AsyncSession) -> Provider:
    """Pick a provider for the legacy /start endpoint based on what
    the admin has enabled. Microsoft wins ties because it's the most
    common ITConnect deployment shape."""
    org = await oidc_svc._load_org(session)
    if org.microsoft_oidc_enabled and org.microsoft_oidc_client_id:
        return "microsoft"
    if org.google_oidc_enabled and org.google_oidc_client_id:
        return "google"
    raise oidc_svc.OidcDisabled("No OIDC provider is enabled.")


@router.get("/providers")
async def list_providers(session: AsyncSession = Depends(db_session)) -> dict:
    """Public — used by the login page to render SSO buttons. Returns
    only labels and start URLs, never credentials."""
    try:
        org = await oidc_svc._load_org(session)
    except oidc_svc.OidcError:
        return {"providers": []}
    return {"providers": oidc_svc.enabled_providers(org)}


async def _start(request: Request, session: AsyncSession, provider: Provider):
    try:
        return await oidc_svc.start_login(request, session, provider=provider)
    except oidc_svc.OidcDisabled as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    except oidc_svc.OidcError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e


async def _callback(
    request: Request,
    response: Response,
    session: AsyncSession,
    provider: Provider,
):
    try:
        claims = await oidc_svc.complete_login(
            request, session, provider=provider
        )
    except oidc_svc.OidcDisabled as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    except Exception as e:
        # authlib raises a variety of errors — bubble them as 401 so the
        # frontend lands on /login with a useful message.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OIDC callback failed: {e}",
        ) from e

    user = await oidc_svc.upsert_user_from_claims(
        session, claims=claims, provider=provider
    )
    access, _exp = auth_svc.issue_access_token(user)
    refresh_raw, _ = await auth_svc.issue_refresh_token(
        session,
        user=user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    await session.commit()

    redirect = RedirectResponse(
        url=f"{settings.PUBLIC_URL.rstrip('/')}/auth/oidc/complete#access_token={access}"
    )
    _set_refresh_cookie(redirect, refresh_raw)
    return redirect


# ---------------- Per-provider routes ----------------


@router.get("/microsoft/start")
async def microsoft_start(
    request: Request, session: AsyncSession = Depends(db_session)
):
    return await _start(request, session, "microsoft")


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    return await _callback(request, response, session, "microsoft")


@router.get("/google/start")
async def google_start(
    request: Request, session: AsyncSession = Depends(db_session)
):
    return await _start(request, session, "google")


@router.get("/google/callback")
async def google_callback(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    return await _callback(request, response, session, "google")


# ---------------- Legacy auto-dispatch ----------------


@router.get("/start")
async def oidc_start_legacy(
    request: Request, session: AsyncSession = Depends(db_session)
):
    try:
        provider = await _resolve_legacy_provider(session)
    except oidc_svc.OidcDisabled as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    return await _start(request, session, provider)


@router.get("/callback")
async def oidc_callback_legacy(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    try:
        provider = await _resolve_legacy_provider(session)
    except oidc_svc.OidcDisabled as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        ) from e
    return await _callback(request, response, session, provider)
