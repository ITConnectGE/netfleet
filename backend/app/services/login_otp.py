"""Login one-time-code: issue + verify + dispatch.

Code is 6 digits with a 5-minute TTL and a 5-attempt counter. The
plaintext is stored only long enough to be dispatched to the user via
SMS or email — the row keeps the argon2 hash and an expiry timestamp.

Channel selection is intentionally simple: prefer SMS when the user
has a mobile number AND the org has the SMS gateway turned on, else
fall back to email. We don't expose the channel choice as a
per-user setting yet — it can be added when the demand shows up.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.organization import Organization
from app.models.user import User
from app.services import email as email_svc
from app.services import sms as sms_svc

log = structlog.get_logger(__name__)

OTP_TTL_SECONDS = 5 * 60
OTP_MAX_ATTEMPTS = 5
OTP_LENGTH = 6


class OtpDispatchError(Exception):
    """Raised when neither SMS nor email could deliver the code. The
    auth layer surfaces this as 503 so the user can retry."""


class OtpInvalid(Exception):
    """Raised when verify_login_otp rejects a code (expired / wrong /
    used up). Always written into the audit log."""


def _new_code() -> str:
    # Zero-padded so "012345" is still 6 chars — important when the
    # user reads the code over the phone.
    return f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"


async def issue_login_otp(
    session: AsyncSession, user: User, *, channel: str
) -> tuple[str, str]:
    """Generate a fresh code, persist a hash + expiry on the user row,
    and dispatch via the requested ``channel`` ("email" or "sms").
    Returns (plaintext, channel_used). The channel is honoured exactly
    — callers that want fallback should retry with the other channel."""
    if channel not in ("email", "sms"):
        raise OtpDispatchError(f"unsupported OTP channel: {channel}")
    code = _new_code()
    user.otp_code_hash = hash_password(code)
    user.otp_expires_at = datetime.now(UTC) + timedelta(seconds=OTP_TTL_SECONDS)
    user.otp_attempts = 0
    await session.flush()
    used = await _dispatch(session, user, code, channel=channel)
    return code, used


async def verify_login_otp(
    session: AsyncSession, user: User, *, code: str
) -> None:
    """Raise OtpInvalid on every failure path. On success clears the code."""
    if not user.otp_code_hash or not user.otp_expires_at:
        raise OtpInvalid("no code outstanding")
    if user.otp_expires_at <= datetime.now(UTC):
        _clear(user)
        await session.flush()
        raise OtpInvalid("code expired")
    if user.otp_attempts >= OTP_MAX_ATTEMPTS:
        _clear(user)
        await session.flush()
        raise OtpInvalid("too many wrong attempts")

    if not verify_password(code, user.otp_code_hash):
        user.otp_attempts += 1
        await session.flush()
        raise OtpInvalid("invalid code")

    _clear(user)
    await session.flush()


def _clear(user: User) -> None:
    user.otp_code_hash = None
    user.otp_expires_at = None
    user.otp_attempts = 0


async def _dispatch(
    session: AsyncSession, user: User, code: str, *, channel: str
) -> str:
    """Send the code via the explicit channel the caller picked. No
    silent fallback: if the user chose SMS but the gateway is dead we
    surface the error so they can re-pick email."""
    org = (
        await session.execute(
            select(Organization).where(Organization.id == user.organization_id)
        )
    ).scalar_one()

    body_text = (
        f"Your NetFleet sign-in code is {code}\n\n"
        f"It expires in {OTP_TTL_SECONDS // 60} minutes. If you didn't try to "
        "sign in, you can ignore this message — but tell your administrator."
    )

    if channel == "sms":
        if not org.mfa_sms_otp_enabled:
            raise OtpDispatchError("SMS sign-in codes are disabled for this organisation.")
        if not user.mobile_phone:
            raise OtpDispatchError("No mobile number on file for this user.")
        if not (org.sms_enabled and org.sms_api_url and org.sms_body_template):
            raise OtpDispatchError("SMS gateway is not configured for this organisation.")
        try:
            await sms_svc.send_sms(
                session,
                user.organization_id,
                destination=user.mobile_phone,
                content=f"NetFleet sign-in code: {code} (valid {OTP_TTL_SECONDS // 60}m)",
            )
            return "sms"
        except sms_svc.SmsGatewayError as e:
            log.warning("login_otp.sms_failed", user_id=str(user.id), error=str(e))
            raise OtpDispatchError(f"SMS gateway failed: {e}") from e

    # channel == "email"
    if not org.mfa_email_otp_enabled:
        raise OtpDispatchError("Email sign-in codes are disabled for this organisation.")
    try:
        await email_svc.send_email(
            org,
            to=user.email,
            subject="Your NetFleet sign-in code",
            body_text=body_text,
        )
        return "email"
    except (email_svc.SmtpNotConfigured, email_svc.SmtpSendError) as e:
        log.warning("login_otp.email_failed", user_id=str(user.id), error=str(e))
        raise OtpDispatchError(f"Email delivery failed: {e}") from e
