"""Authentication endpoints — local login, TOTP, refresh, logout."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, get_current_user
from app.core.config import settings
from app.models.audit_log import AuditOutcome
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponseFinal,
    LoginResponseMfaRequired,
    LoginResponseOtpRequired,
    OtpVerifyRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    TokenPair,
    TotpDisableRequest,
    TotpEnrollConfirmRequest,
    TotpEnrollResponse,
    TotpVerifyRequest,
    UserPublic,
)
from app.services import audit as audit_svc
from app.services import auth as auth_svc
from app.services import email as email_svc
from app.services import login_otp as login_otp_svc

log = structlog.get_logger(__name__)

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
    response_model=LoginResponseFinal | LoginResponseMfaRequired | LoginResponseOtpRequired,
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
    except auth_svc.OtpRequired as e:
        # Look the user back up to dispatch the OTP (auth_svc.OtpRequired
        # carries only IDs, deliberately). We commit immediately so the
        # code + expiry land on the row even if the dispatch fails — the
        # client will still get a temp_token and the user can try again
        # without a fresh password round-trip.
        from uuid import UUID as _UUID
        user = (
            await session.execute(
                select(User).where(User.id == _UUID(e.user_id))
            )
        ).scalar_one()
        try:
            _code, channel = await login_otp_svc.issue_login_otp(session, user)
        except login_otp_svc.OtpDispatchError as err:
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err)
            ) from err
        await session.commit()
        temp, exp = auth_svc.issue_mfa_temp_token_for_id(e.user_id, e.organization_id)
        return LoginResponseOtpRequired(
            mfa_temp_token=temp,
            mfa_temp_expires_at=exp,
            channel=channel,
            destination_hint=_mask_destination(channel, user),
        )
    except auth_svc.AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    return await _finalize_login(session, response, request, user)


@router.post("/otp/verify", response_model=LoginResponseFinal)
async def otp_verify(
    body: OtpVerifyRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    try:
        user = await auth_svc.verify_login_otp_for_user(
            session, mfa_temp_token=body.mfa_temp_token, code=body.code
        )
    except auth_svc.AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    return await _finalize_login(session, response, request, user)


def _mask_destination(channel: str, user: User) -> str:
    """Return a short, non-leaky preview of where the code was sent."""
    if channel == "sms" and user.mobile_phone:
        n = user.mobile_phone
        return f"{'*' * max(0, len(n) - 4)}{n[-4:]}" if len(n) >= 4 else "****"
    if channel == "email":
        local, _, domain = user.email.partition("@")
        if not local or not domain:
            return "****"
        head = local[0] if local else ""
        return f"{head}***@{domain}"
    return "****"


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
    if "otp_login_enabled" in data:
        user.otp_login_enabled = bool(data["otp_login_enabled"])
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
    await session.commit()


@router.post("/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_disable(
    body: TotpDisableRequest,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
):
    try:
        await auth_svc.disable_totp(session, user, current_password=body.current_password)
    except auth_svc.AuthError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="users",
        action="totp_disable",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()


@router.post("/change-password", response_model=TokenPair)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> TokenPair:
    """Self-service password change. Revokes every existing refresh
    token, mints a fresh pair, and sends an SMTP notification (without
    the password itself). Returns a new access token so the caller can
    swap it in without bouncing through /login."""
    try:
        await auth_svc.change_own_password(
            session,
            user=user,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except auth_svc.AuthError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Audit log + commit DB before doing best-effort email — if SMTP is
    # misconfigured we still want the password change to stick.
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="users",
        action="self_password_change",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    # Mint a fresh refresh + access token so the active session is not
    # killed by the bulk revoke we just performed.
    refresh_raw, _ = await auth_svc.issue_refresh_token(
        session,
        user=user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    _set_refresh_cookie(response, refresh_raw)
    access, access_exp = auth_svc.issue_access_token(user)
    await session.commit()

    # Notify the user out-of-band. Failure here is logged but doesn't
    # break the password change — they will have heard about it from
    # the UI already.
    try:
        org = (
            await session.execute(
                select(Organization).where(Organization.id == user.organization_id)
            )
        ).scalar_one()
        await email_svc.send_email(
            org,
            to=user.email,
            subject="Your NetFleet password was changed",
            body_text=(
                "Hi,\n\n"
                "Your NetFleet password was just changed.\n\n"
                f"When: {request.headers.get('date', 'just now')}\n"
                f"From IP: {client_ip(request) or 'unknown'}\n"
                f"Device: {request.headers.get('user-agent', 'unknown')}\n\n"
                "If this wasn't you, contact your administrator immediately.\n"
            ),
        )
    except (email_svc.SmtpNotConfigured, email_svc.SmtpSendError) as e:
        log.warning("password_change.email_failed", user_id=str(user.id), error=str(e))

    return TokenPair(access_token=access, expires_at=access_exp)


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
