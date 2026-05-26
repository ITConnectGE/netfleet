"""OIDC endpoints — only mounted when NETFLEET_OIDC_ENABLED=true."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session
from app.api.v1.auth import _set_refresh_cookie
from app.core.config import settings
from app.services import auth as auth_svc
from app.services import oidc as oidc_svc

router = APIRouter()


@router.get("/start")
async def oidc_start(request: Request):
    if not settings.OIDC_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC not enabled")
    try:
        return await oidc_svc.start_login(request)
    except oidc_svc.OidcDisabled as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/callback")
async def oidc_callback(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    if not settings.OIDC_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC not enabled")
    try:
        claims = await oidc_svc.complete_login(request)
    except Exception as e:  # authlib raises a variety of errors; surface as 401
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"OIDC callback failed: {e}") from e

    user = await oidc_svc.upsert_user_from_claims(session, claims=claims)

    access, access_exp = auth_svc.issue_access_token(user)
    refresh_raw, _ = await auth_svc.issue_refresh_token(
        session,
        user=user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    await session.commit()

    # Redirect to the frontend with the access token in a one-time fragment.
    redirect = RedirectResponse(url=f"{settings.PUBLIC_URL}/auth/oidc/complete#access_token={access}")
    _set_refresh_cookie(redirect, refresh_raw)
    return redirect
