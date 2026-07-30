"""Devices endpoints — CRUD, test-connection, audit logging."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, get_current_user, require_permission
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.device import DeviceCreate, DevicePublic, DeviceUpdate, TestConnectionResult
from app.services import audit as audit_svc
from app.services import device as device_svc
from app.services import device_onboarding as onboarding_svc

router = APIRouter()

# Dropped from the audit payload before it is persisted. `audit._redact`
# also catches these by name, but excluding them here means the plaintext
# never enters the audit path at all. Keep in step with every credential
# field on DeviceCreate / DeviceUpdate.
_CREDENTIAL_FIELDS = {
    "password",
    "api_key",
    "ssh_private_key",
    "become_password",
}


@router.get("", response_model=list[DevicePublic])
async def list_devices(
    site_id: UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[DevicePublic]:
    items = await device_svc.list_devices(session, user.organization_id, site_id=site_id)
    return [device_svc.to_public(d) for d in items]


@router.post("", response_model=DevicePublic, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: DeviceCreate,
    request: Request,
    user: User = Depends(require_permission("devices", "write")),
    session: AsyncSession = Depends(db_session),
) -> DevicePublic:
    try:
        device = await device_svc.create_device(session, user.organization_id, payload)
    except device_svc.UnknownVendor as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except device_svc.SiteNotInOrganization as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except device_svc.DeviceNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    # Redact creds from audit payload
    audit_payload = payload.model_dump(exclude=_CREDENTIAL_FIELDS)
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="devices",
        action="create",
        outcome=AuditOutcome.OK,
        device_id=device.id,
        site_id=device.site_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=audit_payload,
    )
    await session.commit()
    return device_svc.to_public(device)


@router.get("/{device_id}", response_model=DevicePublic)
async def get_device(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> DevicePublic:
    try:
        device = await device_svc.get_device(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return device_svc.to_public(device)


@router.patch("/{device_id}", response_model=DevicePublic)
async def update_device(
    device_id: UUID,
    payload: DeviceUpdate,
    request: Request,
    user: User = Depends(require_permission("devices", "write")),
    session: AsyncSession = Depends(db_session),
) -> DevicePublic:
    try:
        device = await device_svc.update_device(session, user.organization_id, device_id, payload)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except device_svc.SiteNotInOrganization as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    audit_payload = payload.model_dump(exclude_unset=True, exclude=_CREDENTIAL_FIELDS)
    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="devices",
        action="update",
        outcome=AuditOutcome.OK,
        device_id=device.id,
        site_id=device.site_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=audit_payload,
    )
    await session.commit()
    return device_svc.to_public(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: UUID,
    request: Request,
    user: User = Depends(require_permission("devices", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        device = await device_svc.get_device(session, user.organization_id, device_id)
        site_id = device.site_id
        await device_svc.delete_device(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="devices",
        action="delete",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        site_id=site_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()


@router.post("/{device_id}/test-connection", response_model=TestConnectionResult)
async def test_device_connection(
    device_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> TestConnectionResult:
    try:
        result = await device_svc.test_connection(session, user.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="devices",
        action="test_connection",
        outcome=AuditOutcome.OK if result.ok else AuditOutcome.FAILED,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        response_meta={"status": result.status, "identity": result.identity},
        error_message=result.error,
    )
    await session.commit()
    return result


@router.get(
    "/{device_id}/onboarding-script",
    response_class=PlainTextResponse,
)
async def get_onboarding_script(
    device_id: UUID,
    request: Request,
    include_password: bool = Query(default=True),
    user: User = Depends(require_permission("devices", "write")),
    session: AsyncSession = Depends(db_session),
) -> PlainTextResponse:
    """Return a copy-paste script that prepares the device for NetFleet to
    manage it.

    RouterOS: user group + user, IP services + whitelist, firewall rules.
    Linux: management user, NetFleet's public key, sudoers drop-in,
    firewall allow for the SSH port.

    By default the stored RouterOS password is embedded; pass
    ?include_password=false to leave a placeholder instead (audited either
    way as a credential reveal). Linux onboarding is key-based and never
    embeds a secret."""
    try:
        text, extension = await onboarding_svc.generate_script(
            session,
            organization_id=user.organization_id,
            device_id=device_id,
            include_password=include_password,
        )
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="devices",
        action="onboarding_script",
        outcome=AuditOutcome.OK,
        device_id=device_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        response_meta={"include_password": include_password},
    )
    await session.commit()
    return PlainTextResponse(
        text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="netfleet-onboarding-{device_id}.{extension}"'
            ),
        },
    )
