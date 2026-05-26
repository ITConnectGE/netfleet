"""Org-level settings endpoints — currently SMTP."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, require_permission
from app.models.audit_log import AuditOutcome
from app.models.organization import Organization
from app.models.user import User
from app.schemas.settings import (
    SmtpSettingsPublic,
    SmtpSettingsUpdate,
    SmtpTestRequest,
    SmtpTestResult,
)
from app.services import audit as audit_svc
from app.services import email as email_svc
from app.services import settings as settings_svc

router = APIRouter()


def _to_public(org: Organization) -> SmtpSettingsPublic:
    return SmtpSettingsPublic(
        smtp_enabled=org.smtp_enabled,
        smtp_host=org.smtp_host,
        smtp_port=org.smtp_port,
        smtp_username=org.smtp_username,
        smtp_from_email=org.smtp_from_email,
        smtp_from_name=org.smtp_from_name,
        smtp_use_tls=org.smtp_use_tls,
        smtp_use_starttls=org.smtp_use_starttls,
        has_smtp_password=bool(org.smtp_password_encrypted),
    )


@router.get("/smtp", response_model=SmtpSettingsPublic)
async def get_smtp(
    user: User = Depends(require_permission("settings", "read")),
    session: AsyncSession = Depends(db_session),
) -> SmtpSettingsPublic:
    org = await settings_svc.get_organization(session, user.organization_id)
    return _to_public(org)


@router.patch("/smtp", response_model=SmtpSettingsPublic)
async def update_smtp(
    payload: SmtpSettingsUpdate,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> SmtpSettingsPublic:
    org = await settings_svc.update_smtp(session, user.organization_id, payload)

    audit_payload = payload.model_dump(exclude_unset=True, exclude={"smtp_password"})
    if payload.smtp_password is not None:
        audit_payload["smtp_password"] = "***REDACTED***"

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="update_smtp",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=audit_payload,
    )
    await session.commit()
    return _to_public(org)


@router.post("/smtp/test", response_model=SmtpTestResult)
async def test_smtp(
    payload: SmtpTestRequest,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> SmtpTestResult:
    org = await settings_svc.get_organization(session, user.organization_id)
    try:
        await email_svc.send_email(
            org,
            to=str(payload.to),
            subject="NetFleet SMTP test",
            body_text=(
                "This is a test message from NetFleet. "
                "If you received it, SMTP is configured correctly."
            ),
        )
        result = SmtpTestResult(ok=True)
    except (email_svc.SmtpNotConfigured, email_svc.SmtpSendError) as e:
        result = SmtpTestResult(ok=False, error=str(e))

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="test_smtp",
        outcome=AuditOutcome.OK if result.ok else AuditOutcome.FAILED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        response_meta={"to": str(payload.to)},
        error_message=result.error,
    )
    await session.commit()
    return result
