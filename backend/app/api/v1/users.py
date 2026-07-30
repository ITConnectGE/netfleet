"""Users + role-assignment endpoints."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import client_ip, db_session, require_permission
from app.models.audit_log import AuditOutcome
from app.models.organization import Organization
from app.models.user import User
from app.schemas.secret_audit import RiskReport, UnrotatedSecretPublic
from app.schemas.user import (
    AssignmentBulkCreate,
    AssignmentBulkResult,
    AssignmentCreate,
    AssignmentPublic,
    PasswordResetRequest,
    UserCreate,
    UserInviteResponse,
    UserListItem,
    UserUpdate,
)
from app.services import audit as audit_svc
from app.services import secret_audit as secret_audit_svc
from app.services import user as user_svc

router = APIRouter()


def _to_list_item(u: User, count: int) -> UserListItem:
    data = {k: getattr(u, k) for k in UserListItem.model_fields if k != "assignment_count"}
    data["assignment_count"] = count
    return UserListItem.model_validate(data)


@router.get("", response_model=list[UserListItem])
async def list_users(
    user: User = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[UserListItem]:
    items = await user_svc.list_users(session, user.organization_id)
    return [_to_list_item(u, c) for u, c in items]


@router.post("", response_model=UserInviteResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(require_permission("users", "write")),
    session: AsyncSession = Depends(db_session),
) -> UserInviteResponse:
    try:
        new_user, generated = await user_svc.create_user(
            session, actor.organization_id, payload
        )
    except user_svc.UserEmailTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except user_svc.RoleNotInOrganization as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=actor.id,
        organization_id=actor.organization_id,
        section="users",
        action="create",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        # Never log the password — even the auto-generated one. The
        # inviter sees it once in the API response, that's all.
        request_payload={
            **payload.model_dump(exclude={"password"}, mode="json"),
            "password_auto_generated": generated is not None,
        },
    )
    await session.commit()

    # Best-effort welcome email with the credentials inline so the
    # inviter doesn't have to relay the password manually. We send
    # whether the password was generated or supplied — the invitee
    # always needs the URL + username + initial password to sign in.
    email_sent = False
    plaintext = generated or payload.password
    if plaintext:
        org = (
            await session.execute(
                select(Organization).where(Organization.id == actor.organization_id)
            )
        ).scalar_one()
        email_sent = await user_svc.send_invite_email(
            org=org,
            user=new_user,
            plaintext_password=plaintext,
            inviter=actor,
        )

    item = _to_list_item(new_user, len(payload.role_ids))
    return UserInviteResponse(
        user=item, generated_password=generated, email_sent=email_sent
    )


@router.patch("/{user_id}", response_model=UserListItem)
async def update_user(
    user_id: UUID,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(require_permission("users", "write")),
    session: AsyncSession = Depends(db_session),
) -> UserListItem:
    # Self-demotion is refused separately from the last-admin rule: with two
    # admins the org stays administrable, but the person clicking the button
    # would still lock themselves out of every screen they need to undo it.
    if payload.is_admin is False and user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="you cannot remove your own super-admin rights — ask another admin",
        )

    try:
        updated = await user_svc.update_user(session, actor.organization_id, user_id, payload)
    except user_svc.UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except user_svc.LastAdminRemoval as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=actor.id,
        organization_id=actor.organization_id,
        section="users",
        action="update",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return _to_list_item(updated, 0)


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: UUID,
    payload: PasswordResetRequest,
    request: Request,
    actor: User = Depends(require_permission("users", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await user_svc.reset_password(session, actor.organization_id, user_id, payload.new_password)
    except user_svc.UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=actor.id,
        organization_id=actor.organization_id,
        section="users",
        action="reset_password",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={"target_user_id": str(user_id)},
    )
    await session.commit()


# ---------------- assignments ----------------


@router.get("/{user_id}/assignments", response_model=list[AssignmentPublic])
async def list_assignments(
    user_id: UUID,
    actor: User = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[AssignmentPublic]:
    try:
        rows = await user_svc.list_assignments(session, actor.organization_id, user_id)
    except user_svc.UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return [
        AssignmentPublic(
            id=a.id,
            user_id=a.user_id,
            role_id=a.role_id,
            role_name=role_name,
            scope_type=a.scope_type,
            scope_id=a.scope_id,
            scope_label=scope_label,
            expires_at=a.expires_at,
            created_at=a.created_at,
        )
        for a, role_name, scope_label in rows
    ]


@router.post(
    "/{user_id}/assignments",
    response_model=AssignmentPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment(
    user_id: UUID,
    payload: AssignmentCreate,
    request: Request,
    actor: User = Depends(require_permission("users", "write")),
    session: AsyncSession = Depends(db_session),
) -> AssignmentPublic:
    try:
        assignment = await user_svc.create_assignment(
            session, actor.organization_id, user_id, payload
        )
    except user_svc.UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except (user_svc.RoleNotInOrganization, user_svc.InvalidScope) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=actor.id,
        organization_id=actor.organization_id,
        section="users",
        action="assign_role",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "target_user_id": str(user_id),
            **payload.model_dump(mode="json"),
        },
    )
    await session.commit()

    # Re-fetch with the labels resolved
    rows = await user_svc.list_assignments(session, actor.organization_id, user_id)
    for a, role_name, scope_label in rows:
        if a.id == assignment.id:
            return AssignmentPublic(
                id=a.id,
                user_id=a.user_id,
                role_id=a.role_id,
                role_name=role_name,
                scope_type=a.scope_type,
                scope_id=a.scope_id,
                scope_label=scope_label,
                created_at=a.created_at,
            )
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post(
    "/{user_id}/assignments/bulk",
    response_model=AssignmentBulkResult,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_assignments(
    user_id: UUID,
    payload: AssignmentBulkCreate,
    request: Request,
    actor: User = Depends(require_permission("users", "write")),
    session: AsyncSession = Depends(db_session),
) -> AssignmentBulkResult:
    try:
        created, skipped = await user_svc.bulk_create_assignments(
            session, actor.organization_id, user_id, payload
        )
    except user_svc.UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except user_svc.RoleNotInOrganization as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except user_svc.InvalidScope as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=actor.id,
        organization_id=actor.organization_id,
        section="users",
        action="assign_role_bulk",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "target_user_id": str(user_id),
            "role_id": str(payload.role_id),
            "created": len(created),
            "skipped": skipped,
            "scopes": [s.model_dump(mode="json") for s in payload.scopes],
        },
    )
    await session.commit()

    # Re-fetch with labels so the UI doesn't have to plumb three lookups.
    all_rows = await user_svc.list_assignments(
        session, actor.organization_id, user_id
    )
    created_ids = {a.id for a in created}
    new_public = [
        AssignmentPublic(
            id=a.id,
            user_id=a.user_id,
            role_id=a.role_id,
            role_name=role_name,
            scope_type=a.scope_type,
            scope_id=a.scope_id,
            scope_label=scope_label,
            expires_at=a.expires_at,
            created_at=a.created_at,
        )
        for a, role_name, scope_label in all_rows
        if a.id in created_ids
    ]
    return AssignmentBulkResult(
        created=len(created), skipped_existing=skipped, assignments=new_public
    )


@router.delete("/{user_id}/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    user_id: UUID,
    assignment_id: UUID,
    request: Request,
    actor: User = Depends(require_permission("users", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await user_svc.delete_assignment(session, actor.organization_id, user_id, assignment_id)
    except user_svc.UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except user_svc.AssignmentNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=actor.id,
        organization_id=actor.organization_id,
        section="users",
        action="revoke_role",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload={
            "target_user_id": str(user_id),
            "assignment_id": str(assignment_id),
        },
    )
    await session.commit()


# ---------------- risk report ----------------


@router.get("/{user_id}/risk-report", response_model=RiskReport)
async def user_risk_report(
    user_id: UUID,
    actor: User = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(db_session),
) -> RiskReport:
    """Secrets this user revealed and which have NOT been rotated since.

    Use this before disabling a departing employee — the listed secrets should
    be rotated to prevent them from retaining access they once viewed.
    """
    try:
        await user_svc.get_user(session, actor.organization_id, user_id)
    except user_svc.UserNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    items = await secret_audit_svc.user_risk_report(
        session, organization_id=actor.organization_id, user_id=user_id
    )
    return RiskReport(
        user_id=user_id,
        count=len(items),
        items=[UnrotatedSecretPublic(**asdict(s)) for s in items],
    )
