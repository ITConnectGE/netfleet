"""Authentication service — orchestrates login, TOTP, refresh.

Endpoints stay thin; this module owns the business logic and makes it testable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

import pyotp
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    decode_jwt,
    decrypt_field,
    encrypt_field,
    hash_password,
    hash_refresh_token,
    issue_jwt,
    new_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import AuthMethod, User

log = structlog.get_logger(__name__)


class AuthError(Exception):
    """Raised for any auth failure. API layer maps to 401/403."""


class TotpRequired(Exception):
    """Raised when login succeeds password check but user has TOTP enrolled."""

    def __init__(self, user_id: str, organization_id: str) -> None:
        self.user_id = user_id
        self.organization_id = organization_id


class OtpRequired(Exception):
    """Raised when login succeeds password check, TOTP is NOT enrolled,
    but the user has opted into email/SMS OTP. Carries the same IDs as
    TotpRequired so the API layer can mint an mfa_temp token."""

    def __init__(self, user_id: str, organization_id: str) -> None:
        self.user_id = user_id
        self.organization_id = organization_id


# ---------------- Login ----------------


async def authenticate_local(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User:
    """Verify email + password. Raises AuthError on failure, TotpRequired on success-pending-MFA."""
    stmt = select(User).where(User.email == email.lower(), User.is_active.is_(True))
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is None or user.auth_method != AuthMethod.LOCAL:
        # Same timing as a failed verify_password call — argon2 returns in ~50ms
        verify_password(password, None)
        raise AuthError("invalid email or password")

    if not verify_password(password, user.password_hash):
        raise AuthError("invalid email or password")

    if password_needs_rehash(user.password_hash or ""):
        user.password_hash = hash_password(password)
        await session.flush()

    # The login endpoint decides whether MFA is needed by inspecting
    # user.totp_enrolled / user.otp_login_enabled — we don't raise from
    # here anymore so the caller can present a method picker when the
    # user has multiple options. The legacy TotpRequired / OtpRequired
    # exceptions stay defined for any external caller still expecting
    # them, but our /auth/login path no longer raises them.
    return user


def available_mfa_methods(
    user: User, organization
) -> list[tuple[str, str | None]]:
    """Return the ordered list of MFA methods this user can use right
    now, as (method, destination_hint) tuples. Priority: TOTP first,
    then email, then SMS — matches what an operator expects under
    "which factor should I use today?".

    ``destination_hint`` is None for TOTP (no out-of-band delivery) and
    a masked label for email / SMS (so the picker UI can show "code to
    n***@example.com" without leaking the full address)."""
    out: list[tuple[str, str | None]] = []
    if user.totp_enrolled:
        out.append(("totp", None))
    if user.otp_login_enabled:
        local, _, domain = user.email.partition("@")
        head = local[0] if local else ""
        email_hint = f"{head}***@{domain}" if domain else "****"
        out.append(("email", email_hint))
        # SMS only when both the user has a mobile AND the org has the
        # gateway turned on + configured.
        sms_ready = bool(
            user.mobile_phone
            and getattr(organization, "sms_enabled", False)
            and getattr(organization, "sms_api_url", None)
            and getattr(organization, "sms_body_template", None)
        )
        if sms_ready:
            n = user.mobile_phone or ""
            sms_hint = (
                f"{'*' * max(0, len(n) - 4)}{n[-4:]}" if len(n) >= 4 else "****"
            )
            out.append(("sms", sms_hint))
    return out


# ---------------- TOTP ----------------


def make_totp_secret() -> str:
    return pyotp.random_base32()


def make_otpauth_uri(secret: str, email: str, issuer: str = "NetFleet") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret_plain: str, code: str) -> bool:
    return pyotp.TOTP(secret_plain).verify(code, valid_window=1)


async def verify_totp_for_user(
    session: AsyncSession,
    *,
    mfa_temp_token: str,
    code: str,
) -> User:
    try:
        payload = decode_jwt(mfa_temp_token, expected_type="mfa_temp")
    except ValueError as e:
        raise AuthError(str(e)) from e

    user_id = payload["sub"]
    stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None or not user.totp_enrolled or not user.totp_secret_encrypted:
        raise AuthError("totp not configured for this user")

    secret = decrypt_field(user.totp_secret_encrypted)
    if not verify_totp(secret, code):
        raise AuthError("invalid TOTP code")

    return user


async def verify_login_otp_for_user(
    session: AsyncSession,
    *,
    mfa_temp_token: str,
    code: str,
) -> User:
    # Imported lazily — the OTP service depends on email/sms services,
    # and auth.py is the lowest layer in the dep graph.
    from app.services import login_otp as login_otp_svc

    try:
        payload = decode_jwt(mfa_temp_token, expected_type="mfa_temp")
    except ValueError as e:
        raise AuthError(str(e)) from e

    user_id = payload["sub"]
    stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None or not user.otp_login_enabled:
        raise AuthError("otp login not configured for this user")

    try:
        await login_otp_svc.verify_login_otp(session, user, code=code)
    except login_otp_svc.OtpInvalid as e:
        raise AuthError(str(e)) from e

    return user


# ---------------- Token issuance ----------------


def issue_mfa_temp_token(user: User) -> tuple[str, datetime]:
    return issue_mfa_temp_token_for_id(str(user.id), str(user.organization_id))


def issue_mfa_temp_token_for_id(user_id: str, organization_id: str) -> tuple[str, datetime]:
    return issue_jwt(
        subject=user_id,
        organization_id=organization_id,
        token_type="mfa_temp",
        ttl_seconds=300,  # 5 minutes to complete TOTP
    )


def issue_access_token(user: User) -> tuple[str, datetime]:
    return issue_jwt(
        subject=user.id,
        organization_id=user.organization_id,
        token_type="access",
        extra_claims={"adm": user.is_admin},
    )


async def issue_refresh_token(
    session: AsyncSession,
    *,
    user: User,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[str, datetime]:
    raw, h = new_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.REFRESH_TOKEN_TTL)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=h,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    )
    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return raw, expires_at


async def rotate_refresh_token(
    session: AsyncSession,
    *,
    presented_raw: str,
    user_agent: str | None,
    ip_address: str | None,
) -> tuple[User, str, datetime]:
    h = hash_refresh_token(presented_raw)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == h)
    rt = (await session.execute(stmt)).scalar_one_or_none()

    if rt is None:
        raise AuthError("unknown refresh token")
    if rt.revoked_at is not None:
        # Reuse of a revoked token — possible theft. Revoke everything for this user.
        await _revoke_all_for_user(session, rt.user_id)
        raise AuthError("refresh token reuse detected; all sessions revoked")
    if rt.expires_at <= datetime.now(UTC):
        raise AuthError("refresh token expired")

    user = await session.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise AuthError("user inactive")

    # Rotate
    new_raw, new_hash = new_refresh_token()
    new_expires = datetime.now(UTC) + timedelta(seconds=settings.REFRESH_TOKEN_TTL)
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=new_expires,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    session.add(new_rt)
    await session.flush()

    rt.revoked_at = datetime.now(UTC)
    rt.replaced_by_id = new_rt.id
    await session.flush()

    return user, new_raw, new_expires


async def revoke_refresh_token(session: AsyncSession, presented_raw: str) -> None:
    h = hash_refresh_token(presented_raw)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == h)
    rt = (await session.execute(stmt)).scalar_one_or_none()
    if rt and rt.revoked_at is None:
        rt.revoked_at = datetime.now(UTC)
        await session.flush()


async def _revoke_all_for_user(session: AsyncSession, user_id) -> None:
    stmt = select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    now = datetime.now(UTC)
    for rt in (await session.execute(stmt)).scalars():
        rt.revoked_at = now
    await session.flush()


# ---------------- TOTP enrollment ----------------


async def begin_totp_enrollment(session: AsyncSession, user: User) -> tuple[str, str]:
    """Generate a TOTP secret, store it (encrypted), return (secret, otpauth_uri).
    The user must POST a valid code to confirm before totp_enrolled flips to True."""
    secret = make_totp_secret()
    user.totp_secret_encrypted = encrypt_field(secret)
    user.totp_enrolled = False
    await session.flush()
    return secret, make_otpauth_uri(secret, user.email)


async def confirm_totp_enrollment(session: AsyncSession, user: User, code: str) -> Literal[True]:
    if not user.totp_secret_encrypted:
        raise AuthError("no TOTP enrollment in progress")
    secret = decrypt_field(user.totp_secret_encrypted)
    if not verify_totp(secret, code):
        raise AuthError("invalid TOTP code")
    user.totp_enrolled = True
    await session.flush()
    return True


async def disable_totp(
    session: AsyncSession, user: User, *, current_password: str
) -> None:
    """Operator-initiated TOTP removal. Re-checks the password so a
    stolen-but-unlocked session can't unwind the second factor."""
    if not verify_password(current_password, user.password_hash):
        raise AuthError("invalid current password")
    user.totp_secret_encrypted = None
    user.totp_enrolled = False
    await session.flush()


# ---------------- Password change ----------------


async def change_own_password(
    session: AsyncSession,
    *,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    """Self-service password change.

    Validates the current password, hashes the new one, clears the
    must_change_password gate, and revokes every refresh token this user
    owns so other sessions are kicked out. The caller (API layer) is
    responsible for issuing a fresh refresh token afterwards if it
    wants the active session to survive."""
    if user.auth_method != AuthMethod.LOCAL:
        raise AuthError("only local accounts can change password here")
    if not verify_password(current_password, user.password_hash):
        raise AuthError("current password is incorrect")
    if current_password == new_password:
        raise AuthError("new password must differ from current password")

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await _revoke_all_for_user(session, user.id)
    await session.flush()
