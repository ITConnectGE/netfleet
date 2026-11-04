"""Authentication service — orchestrates login, TOTP, refresh.

Endpoints stay thin; this module owns the business logic and makes it testable.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import pyotp
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.request_context import current_session_id
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
    n***@example.com" without leaking the full address).

    Org-wide MFA toggles in Settings → Authorization are honoured here
    so a globally-disabled factor never shows up in the picker, even
    if individual users still have the enrolment bit set."""
    out: list[tuple[str, str | None]] = []
    totp_allowed = getattr(organization, "mfa_totp_enabled", True)
    email_allowed = getattr(organization, "mfa_email_otp_enabled", True)
    sms_allowed = getattr(organization, "mfa_sms_otp_enabled", True)

    if user.totp_enrolled and totp_allowed:
        out.append(("totp", None))
    if user.otp_login_enabled:
        if email_allowed:
            local, _, domain = user.email.partition("@")
            head = local[0] if local else ""
            email_hint = f"{head}***@{domain}" if domain else "****"
            out.append(("email", email_hint))
        # SMS only when both the user has a mobile AND the org has the
        # gateway turned on + configured.
        sms_ready = bool(
            sms_allowed
            and user.mobile_phone
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


TOTP_MAX_FAILED_ATTEMPTS = 5
TOTP_LOCKOUT = timedelta(minutes=15)


def matching_totp_step(secret_plain: str, code: str, now: datetime) -> int | None:
    """The 30 s time step `code` is valid for (±1 step of drift), or None."""
    totp = pyotp.TOTP(secret_plain)
    base = totp.timecode(now)
    for offset in (0, -1, 1):
        if hmac.compare_digest(totp.at(now, counter_offset=offset), code):
            return base + offset
    return None


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

    now = datetime.now(UTC)
    if user.totp_locked_until and user.totp_locked_until > now:
        minutes = int((user.totp_locked_until - now).total_seconds() // 60) + 1
        raise AuthError(f"too many wrong codes — try again in {minutes} min")

    # Callers must commit even when this raises, so failed attempts stick.
    secret = decrypt_field(user.totp_secret_encrypted)
    step = matching_totp_step(secret, code.strip(), now)
    if step is None:
        user.totp_failed_attempts += 1
        if user.totp_failed_attempts >= TOTP_MAX_FAILED_ATTEMPTS:
            user.totp_failed_attempts = 0
            user.totp_locked_until = now + TOTP_LOCKOUT
            log.warning("auth.totp_locked", user_id=str(user.id))
        await session.flush()
        raise AuthError("invalid TOTP code")
    if user.totp_last_step is not None and step <= user.totp_last_step:
        raise AuthError("this code was already used — wait for the next one")

    user.totp_last_step = step
    user.totp_failed_attempts = 0
    user.totp_locked_until = None
    await session.flush()
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


def issue_access_token(user: User, session_id: UUID | None = None) -> tuple[str, datetime]:
    """Access token for `user`. It carries the sign-in session as `sid` —
    the one passed in, else the one this request started or belongs to."""
    sid = session_id or current_session_id.get()
    claims: dict[str, object] = {"adm": user.is_admin}
    if sid is not None:
        claims["sid"] = str(sid)
    return issue_jwt(
        subject=user.id,
        organization_id=user.organization_id,
        token_type="access",
        extra_claims=claims,
    )


async def issue_refresh_token(
    session: AsyncSession,
    *,
    user: User,
    user_agent: str | None,
    ip_address: str | None,
    session_id: UUID | None = None,
) -> tuple[str, datetime]:
    """Start a sign-in session (or continue `session_id`) with a fresh
    refresh token. The session id becomes the request's current session,
    so the access token and audit rows issued next carry it."""
    raw, h = new_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.REFRESH_TOKEN_TTL)
    sid = session_id or uuid4()
    current_session_id.set(sid)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=h,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            session_id=sid,
        )
    )
    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return raw, expires_at


# How long a just-rotated refresh token is still accepted. Long enough to
# cover parallel tabs and a lost response, short enough that a stolen
# token replayed later still trips reuse detection.
REFRESH_REUSE_GRACE_SECONDS = 60


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
        if rt.replaced_by_id is None:
            # Revoked by logout / password change, not by rotation. Not a
            # theft signal — just a dead session.
            raise AuthError("refresh token revoked")
        age = (datetime.now(UTC) - rt.revoked_at).total_seconds()
        if age > REFRESH_REUSE_GRACE_SECONDS:
            # A token rotated away long ago is being replayed — possible
            # theft. Revoke everything for this user.
            await _revoke_all_for_user(session, rt.user_id)
            raise AuthError("refresh token reuse detected; all sessions revoked")
        # Rotated moments ago: two tabs refreshed with the same cookie, or
        # the response carrying the new cookie never reached the browser
        # (reload, network blip, API restart). Treating that as theft
        # logged the operator out of every session, so a sibling may be
        # minted — but only while the session this token belongs to is
        # still alive. Logout and revoke-all (password change, reuse
        # detection) kill the live tip of the chain without a successor;
        # a recently rotated ancestor must not be able to resurrect it.
        if not await _chain_is_live(session, rt):
            raise AuthError("refresh token revoked")
    if rt.expires_at <= datetime.now(UTC):
        raise AuthError("refresh token expired")

    user = await session.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise AuthError("user inactive")

    # Rotate
    new_raw, new_hash = new_refresh_token()
    new_expires = datetime.now(UTC) + timedelta(seconds=settings.REFRESH_TOKEN_TTL)
    if rt.revoked_at is not None:
        # A grace-window sibling never outlives the token it came from.
        new_expires = min(new_expires, rt.expires_at)
    # Tokens minted before sessions were tracked start one on first refresh.
    sid = rt.session_id or uuid4()
    current_session_id.set(sid)
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=new_expires,
        user_agent=user_agent,
        ip_address=ip_address,
        session_id=sid,
    )
    session.add(new_rt)
    await session.flush()

    if rt.revoked_at is None:
        rt.revoked_at = datetime.now(UTC)
        rt.replaced_by_id = new_rt.id
        await session.flush()

    return user, new_raw, new_expires


# Rotation chains are one hop per refresh; a live chain more than a few
# hops past a token rotated under a minute ago is not a real session.
_MAX_CHAIN_HOPS = 32


async def _chain_is_live(session: AsyncSession, rt: RefreshToken) -> bool:
    """Follow `replaced_by_id` from a rotated token to the newest token of
    its session. The session is live only if that newest token is
    unrevoked and unexpired. A token revoked without a successor (logout,
    revoke-all) ends the chain dead."""
    current = rt
    for _ in range(_MAX_CHAIN_HOPS):
        if current.revoked_at is None:
            return current.expires_at > datetime.now(UTC)
        if current.replaced_by_id is None:
            return False
        nxt = await session.get(RefreshToken, current.replaced_by_id)
        if nxt is None:
            return False
        current = nxt
    return False


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
