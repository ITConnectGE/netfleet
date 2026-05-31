"""Authentication endpoints — local login, TOTP, refresh, logout."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, get_current_user
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponseFinal,
    LoginResponseMfaRequired,
    ProfileUpdateRequest,
    RefreshRequest,
    TokenPair,
    TotpEnrollConfirmRequest,
    TotpEnrollResponse,
    TotpVerifyRequest,
    UserPublic,
)
from app.services import auth as auth_svc

router = APIRouter()

REFRESH_COOKIE = "netfleet_refresh"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw,
        max_age=settings.REFRESH_TOKEN_TTL,
        httponly=True,
        secure=settings.ENV == "production",
        samesite="lax",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.post(
    "/login",
    response_model=LoginResponseFinal | LoginResponseMfaRequired,
    responses={401: {"description": "invalid credentials"}},
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    try:
        user = await auth_svc.authenticate_local(session, email=body.email, password=body.password)
    except auth_svc.TotpRequired as e:
        # Issue a short-lived MFA temp token; client posts it back with the code.
        temp, exp = auth_svc.issue_mfa_temp_token_for_id(e.user_id, e.organization_id)
        return LoginResponseMfaRequired(mfa_temp_token=temp, mfa_temp_expires_at=exp)
    except auth_svc.AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    return await _finalize_login(session, response, request, user)


@router.post("/totp/verify", response_model=LoginResponseFinal)
async def totp_verify(
    body: TotpVerifyRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    try:
        user = await auth_svc.verify_totp_for_user(
            session, mfa_temp_token=body.mfa_temp_token, code=body.code
        )
    except auth_svc.AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    return await _finalize_login(session, response, request, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
    netfleet_refresh: str | None = Cookie(default=None),
):
    presented = body.refresh_token or netfleet_refresh
    if not presented:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing refresh token")
    try:
        user, new_raw, _ = await auth_svc.rotate_refresh_token(
            session,
            presented_raw=presented,
            user_agent=request.headers.get("user-agent"),
            ip_address=client_ip(request),
        )
    except auth_svc.AuthError as e:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    access, access_exp = auth_svc.issue_access_token(user)
    _set_refresh_cookie(response, new_raw)
    return TokenPair(access_token=access, expires_at=access_exp)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session: AsyncSession = Depends(db_session),
    netfleet_refresh: str | None = Cookie(default=None),
):
    if netfleet_refresh:
        await auth_svc.revoke_refresh_token(session, netfleet_refresh)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserPublic)
async def update_me(
    body: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> User:
    data = body.model_dump(exclude_unset=True)
    if "display_name" in data:
        user.display_name = data["display_name"]
    if "mobile_phone" in data:
        raw = data["mobile_phone"]
        if raw is not None:
            # Strip whitespace + common separators; keep leading "+".
            cleaned = "".join(c for c in raw if c.isdigit() or c == "+")
            user.mobile_phone = cleaned or None
        else:
            user.mobile_phone = None
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/totp/enroll", response_model=TotpEnrollResponse)
async def totp_enroll_begin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
):
    if user.totp_enrolled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="TOTP already enrolled")
    secret, uri = await auth_svc.begin_totp_enrollment(session, user)
    return TotpEnrollResponse(secret=secret, otpauth_uri=uri)


@router.post("/totp/enroll/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def totp_enroll_confirm(
    body: TotpEnrollConfirmRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
):
    try:
        await auth_svc.confirm_totp_enrollment(session, user, body.code)
    except auth_svc.AuthError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


# ---------------- helpers ----------------


async def _finalize_login(
    session: AsyncSession,
    response: Response,
    request: Request,
    user: User,
) -> LoginResponseFinal:
    access, access_exp = auth_svc.issue_access_token(user)
    refresh_raw, _ = await auth_svc.issue_refresh_token(
        session,
        user=user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    _set_refresh_cookie(response, refresh_raw)
    await session.commit()
    return LoginResponseFinal(
        access_token=access,
        expires_at=access_exp,
        user=UserPublic.model_validate(user),
    )
