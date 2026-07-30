"""Audit log helper — write every privileged action into audit_logs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog, AuditOutcome

# Keys we strip from payloads before persisting — never write secrets to audit_log.
_SECRET_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "passwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "totp_secret",
        "fernet_key",
        "jwt_secret",
    }
)

# Substrings that mark a field as secret wherever they appear in its name.
# Exact-match alone is fail-open: it silently misses every prefixed or
# suffixed variant a new schema introduces (`become_password`,
# `ssh_private_key`, `smtp_password`), and the miss is invisible until
# someone reads the audit log. Matching on substrings makes the next
# credential field added anywhere safe by default.
_SECRET_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "token",
    "private_key",
    "privatekey",
    "passphrase",
    "credential",
)


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _SECRET_KEYS:
        return True
    return any(marker in lowered for marker in _SECRET_SUBSTRINGS)


def _redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            k: ("***REDACTED***" if _is_secret_key(k) else _redact(v))
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [_redact(v) for v in payload]
    return payload


async def write_audit(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    organization_id: UUID | None,
    section: str,
    action: str,
    outcome: AuditOutcome = AuditOutcome.OK,
    device_id: UUID | None = None,
    site_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_payload: dict[str, Any] | None = None,
    response_meta: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user_id,
            organization_id=organization_id,
            section=section,
            action=action,
            outcome=outcome,
            device_id=device_id,
            site_id=site_id,
            ip_address=ip_address,
            user_agent=user_agent[:512] if user_agent else None,
            request_payload=_redact(request_payload) if request_payload else None,
            response_meta=response_meta,
            error_message=error_message[:1024] if error_message else None,
        )
    )
    await session.flush()
