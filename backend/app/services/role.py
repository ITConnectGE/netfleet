"""Role service — CRUD on Roles and Permissions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.role import Permission, Role, RoleAssignment
from app.schemas.role import PermissionInput, RoleCreate, RoleUpdate


class RoleNotFound(Exception):
    pass


class RoleNameTaken(Exception):
    pass


class SystemRoleImmutable(Exception):
    """System roles can't have their core fields edited via the API."""


async def list_roles(session: AsyncSession, organization_id: UUID) -> list[tuple[Role, int]]:
    stmt = (
        select(Role, func.count(RoleAssignment.id))
        .outerjoin(RoleAssignment, RoleAssignment.role_id == Role.id)
        .where(Role.organization_id == organization_id)
        .options(selectinload(Role.permissions))
        .group_by(Role.id)
        .order_by(Role.is_system.desc(), Role.name)
    )
    result = await session.execute(stmt)
    return [(r, int(c or 0)) for r, c in result.all()]


async def get_role(session: AsyncSession, organization_id: UUID, role_id: UUID) -> Role:
    stmt = (
        select(Role)
        .where(Role.id == role_id, Role.organization_id == organization_id)
        .options(selectinload(Role.permissions))
    )
    role = (await session.execute(stmt)).scalar_one_or_none()
    if role is None:
        raise RoleNotFound("role not found")
    return role


async def create_role(
    session: AsyncSession,
    organization_id: UUID,
    payload: RoleCreate,
) -> Role:
    dupe = (
        await session.execute(
            select(Role.id).where(
                Role.organization_id == organization_id, Role.name == payload.name
            )
        )
    ).first()
    if dupe is not None:
        raise RoleNameTaken(f"role '{payload.name}' already exists")

    role = Role(
        organization_id=organization_id,
        name=payload.name,
        description=payload.description,
        is_system=False,
    )
    session.add(role)
    await session.flush()
    _sync_permissions(session, role, payload.permissions)
    await session.flush()
    return await get_role(session, organization_id, role.id)


async def update_role(
    session: AsyncSession,
    organization_id: UUID,
    role_id: UUID,
    payload: RoleUpdate,
) -> Role:
    role = await get_role(session, organization_id, role_id)

    if role.is_system and (payload.name is not None or payload.permissions is not None):
        raise SystemRoleImmutable("system roles: only description may be edited")

    if payload.name is not None and payload.name != role.name:
        dupe = (
            await session.execute(
                select(Role.id).where(
                    Role.organization_id == organization_id,
                    Role.name == payload.name,
                    Role.id != role.id,
                )
            )
        ).first()
        if dupe is not None:
            raise RoleNameTaken(f"role '{payload.name}' already exists")
        role.name = payload.name

    if payload.description is not None:
        role.description = payload.description

    if payload.permissions is not None:
        # remove all and re-add (simplest correct behaviour)
        for p in role.permissions:
            await session.delete(p)
        await session.flush()
        _sync_permissions(session, role, payload.permissions)

    await session.flush()
    return await get_role(session, organization_id, role.id)


async def delete_role(session: AsyncSession, organization_id: UUID, role_id: UUID) -> None:
    role = await get_role(session, organization_id, role_id)
    if role.is_system:
        raise SystemRoleImmutable("system roles cannot be deleted")
    await session.delete(role)
    await session.flush()


def _sync_permissions(
    session: AsyncSession,
    role: Role,
    permissions: list[PermissionInput],
) -> None:
    """Add Permission rows. Caller is responsible for clearing the prior set."""
    seen: set[tuple[str, str]] = set()
    for p in permissions:
        key = (p.section, p.action.value)
        if key in seen:
            continue
        seen.add(key)
        session.add(Permission(role_id=role.id, section=p.section, action=p.action))
