"""Org-level settings endpoints — currently SMTP."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, require_permission
from app.models.audit_log import AuditOutcome
from app.models.organization import Organization
from app.models.user import User
from app.schemas.settings import (
    OrgInfoPublic,
    OrgInfoUpdate,
    SmsProviderPreset,
    SmsSettingsPublic,
    SmsSettingsUpdate,
    SmsTestRequest,
    SmsTestResult,
    SmtpSettingsPublic,
    SmtpSettingsUpdate,
    SmtpTestRequest,
    SmtpTestResult,
)
from app.services import audit as audit_svc
from app.services import email as email_svc
from app.services import settings as settings_svc
from app.services import sms as sms_svc

router = APIRouter()


# ---------------- Org info (NetFleet's own external IP(s)) ----------------


@router.get("/org-info", response_model=OrgInfoPublic)
async def get_org_info(
    user: User = Depends(require_permission("settings", "read")),
    session: AsyncSession = Depends(db_session),
) -> OrgInfoPublic:
    org = await settings_svc.get_organization(session, user.organization_id)
    return OrgInfoPublic(netfleet_external_ips=org.netfleet_external_ips)


@router.patch("/org-info", response_model=OrgInfoPublic)
async def patch_org_info(
    payload: OrgInfoUpdate,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> OrgInfoPublic:
    org = await settings_svc.update_org_info(
        session,
        user.organization_id,
        netfleet_external_ips=payload.netfleet_external_ips,
    )
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="update_org_info",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return OrgInfoPublic(netfleet_external_ips=org.netfleet_external_ips)


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


# ---------------- SMS gateway ----------------


def _sms_to_public(org: Organization) -> SmsSettingsPublic:
    return SmsSettingsPublic(
        sms_enabled=org.sms_enabled,
        sms_provider=org.sms_provider,
        sms_api_url=org.sms_api_url,
        sms_http_method=org.sms_http_method,
        sms_body_format=org.sms_body_format,
        sms_body_template=org.sms_body_template,
        sms_auth_header_name=org.sms_auth_header_name,
        sms_auth_header_value_template=org.sms_auth_header_value_template,
        sms_sender=org.sms_sender,
        sms_success_status_min=org.sms_success_status_min,
        sms_success_status_max=org.sms_success_status_max,
        sms_success_body_contains=org.sms_success_body_contains,
        sms_timeout_seconds=org.sms_timeout_seconds,
        has_sms_api_key=bool(org.sms_api_key_encrypted),
        sms_last_test_at=org.sms_last_test_at,
        sms_last_test_ok=org.sms_last_test_ok,
        sms_last_test_message=org.sms_last_test_message,
    )


@router.get("/sms/presets", response_model=list[SmsProviderPreset])
async def list_sms_presets(
    _: User = Depends(require_permission("settings", "read")),
) -> list[SmsProviderPreset]:
    return [SmsProviderPreset(**p) for p in sms_svc.list_presets()]


@router.get("/sms", response_model=SmsSettingsPublic)
async def get_sms(
    user: User = Depends(require_permission("settings", "read")),
    session: AsyncSession = Depends(db_session),
) -> SmsSettingsPublic:
    org = await settings_svc.get_organization(session, user.organization_id)
    return _sms_to_public(org)


@router.patch("/sms", response_model=SmsSettingsPublic)
async def update_sms(
    payload: SmsSettingsUpdate,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> SmsSettingsPublic:
    org = await sms_svc.update_sms(session, user.organization_id, payload)

    audit_payload = payload.model_dump(exclude_unset=True, exclude={"sms_api_key"})
    if payload.sms_api_key is not None:
        audit_payload["sms_api_key"] = "***REDACTED***"

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="update_sms",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=audit_payload,
    )
    await session.commit()
    return _sms_to_public(org)


@router.post("/sms/test", response_model=SmsTestResult)
async def test_sms(
    payload: SmsTestRequest,
    request: Request,
    user: User = Depends(require_permission("settings", "write")),
    session: AsyncSession = Depends(db_session),
) -> SmsTestResult:
    ok, status_code, body, err = await sms_svc.test_sms(
        session,
        user.organization_id,
        destination=payload.to,
        content=payload.content,
    )

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="settings",
        action="test_sms",
        outcome=AuditOutcome.OK if ok else AuditOutcome.FAILED,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        response_meta={"to": payload.to, "http_status": status_code},
        error_message=err,
    )
    await session.commit()
    return SmsTestResult(
        ok=ok,
        http_status=status_code,
        response_body=body,
        error=err,
    )
