"""Cryptographic primitives — keep all sensitive operations behind this module."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from app.core.config import settings

# ---------- Password hashing (Argon2id) ----------

_ph = PasswordHasher()


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        _ph.verify(password_hash, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return True


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# ---------- Symmetric field encryption (Fernet) ----------

_fernet = Fernet(settings.FERNET_KEY.encode() if isinstance(settings.FERNET_KEY, str) else settings.FERNET_KEY)


def encrypt_field(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt_field(token: str) -> str:
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("invalid encrypted value") from e


# ---------- JWT (access tokens) ----------

JWT_ALG = "HS256"

TokenType = Literal["access", "mfa_temp"]


def issue_jwt(
    *,
    subject: UUID | str,
    organization_id: UUID | str,
    token_type: TokenType = "access",
    extra_claims: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> tuple[str, datetime]:
    """Issue a signed JWT. Returns (token, expires_at_utc)."""
    now = datetime.now(UTC)
    ttl = ttl_seconds if ttl_seconds is not None else settings.ACCESS_TOKEN_TTL
    exp = now + timedelta(seconds=ttl)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "org": str(organization_id),
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALG), exp


def decode_jwt(token: str, expected_type: TokenType = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise ValueError(f"invalid token: {e}") from e

    if payload.get("typ") != expected_type:
        raise ValueError(f"wrong token type: expected {expected_type}, got {payload.get('typ')!r}")

    return payload


# ---------- Refresh tokens (opaque) ----------

def new_refresh_token() -> tuple[str, str]:
    """Generate a new opaque refresh token. Returns (raw, hash) — store the hash, give the raw to the client."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    """SHA-256 hash for refresh tokens (constant-time comparable, lookup-friendly)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
