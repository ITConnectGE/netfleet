"""Roles + section catalog endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    client_ip,
    db_session,
    get_current_user,
    require_permission,
)
from app.models.audit_log import AuditOutcome
from app.models.user import User
from app.schemas.role import (
    PermissionPublic,
    RoleCreate,
    RolePublic,
    RoleUpdate,
    SectionInfo,
)
from app.services import audit as audit_svc
from app.services import role as role_svc
from app.services.rbac import APP_SECTIONS, DRIVER_SECTIONS

router = APIRouter()


def _to_public(role, assignment_count: int = 0) -> RolePublic:
    return RolePublic(
        id=role.id,
        organization_id=role.organization_id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=[
            PermissionPublic(id=p.id, section=p.section, action=p.action) for p in role.permissions
        ],
        assignment_count=assignment_count,
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.get("/sections", response_model=list[SectionInfo])
async def list_sections(_: User = Depends(get_current_user)) -> list[SectionInfo]:
    out: list[SectionInfo] = []
    for sec, actions in APP_SECTIONS.items():
        out.append(SectionInfo(section=sec, actions=actions, kind="app"))
    for sec, actions in DRIVER_SECTIONS.items():
        out.append(SectionInfo(section=sec, actions=actions, kind="driver"))
    return out


@router.get("", response_model=list[RolePublic])
async def list_roles(
    user: User = Depends(require_permission("roles", "read")),
    session: AsyncSession = Depends(db_session),
) -> list[RolePublic]:
    items = await role_svc.list_roles(session, user.organization_id)
    return [_to_public(r, c) for r, c in items]


@router.post("", response_model=RolePublic, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    request: Request,
    user: User = Depends(require_permission("roles", "write")),
    session: AsyncSession = Depends(db_session),
) -> RolePublic:
    try:
        role = await role_svc.create_role(session, user.organization_id, payload)
    except role_svc.RoleNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="roles",
        action="create",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(),
    )
    await session.commit()
    return _to_public(role, 0)


@router.get("/{role_id}", response_model=RolePublic)
async def get_role(
    role_id: UUID,
    user: User = Depends(require_permission("roles", "read")),
    session: AsyncSession = Depends(db_session),
) -> RolePublic:
    try:
        role = await role_svc.get_role(session, user.organization_id, role_id)
    except role_svc.RoleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _to_public(role)


@router.patch("/{role_id}", response_model=RolePublic)
async def update_role(
    role_id: UUID,
    payload: RoleUpdate,
    request: Request,
    user: User = Depends(require_permission("roles", "write")),
    session: AsyncSession = Depends(db_session),
) -> RolePublic:
    try:
        role = await role_svc.update_role(session, user.organization_id, role_id, payload)
    except role_svc.RoleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except role_svc.RoleNameTaken as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except role_svc.SystemRoleImmutable as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="roles",
        action="update",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(exclude_unset=True),
    )
    await session.commit()
    return _to_public(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    request: Request,
    user: User = Depends(require_permission("roles", "write")),
    session: AsyncSession = Depends(db_session),
) -> None:
    try:
        await role_svc.delete_role(session, user.organization_id, role_id)
    except role_svc.RoleNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except role_svc.SystemRoleImmutable as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="roles",
        action="delete",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
