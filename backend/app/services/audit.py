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


def _redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            k: ("***REDACTED***" if k.lower() in _SECRET_KEYS else _redact(v))
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
