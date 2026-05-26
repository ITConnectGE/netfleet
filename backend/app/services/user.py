"""User + role-assignment service."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_password
from app.models.device import Device
from app.models.role import AssignmentScope, Role, RoleAssignment
from app.models.site import Site
from app.models.user import AuthMethod, User
from app.schemas.user import AssignmentCreate, UserCreate, UserUpdate


class UserNotFound(Exception):
    pass


class UserEmailTaken(Exception):
    pass


class RoleNotInOrganization(Exception):
    pass


class InvalidScope(Exception):
    pass


class AssignmentNotFound(Exception):
    pass


# ---------------- users ----------------


async def list_users(
    session: AsyncSession, organization_id: UUID
) -> list[tuple[User, int]]:
    stmt = (
        select(User, func.count(RoleAssignment.id))
        .outerjoin(RoleAssignment, RoleAssignment.user_id == User.id)
        .where(User.organization_id == organization_id)
        .group_by(User.id)
        .order_by(User.email)
    )
    return [(u, int(c or 0)) for u, c in (await session.execute(stmt)).all()]


async def get_user(session: AsyncSession, organization_id: UUID, user_id: UUID) -> User:
    stmt = select(User).where(User.id == user_id, User.organization_id == organization_id)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise UserNotFound("user not found")
    return user


async def create_user(
    session: AsyncSession, organization_id: UUID, payload: UserCreate
) -> User:
    email = payload.email.lower()
    dupe = (
        await session.execute(
            select(User.id).where(
                User.organization_id == organization_id, User.email == email
            )
        )
    ).first()
    if dupe is not None:
        raise UserEmailTaken(f"user with email '{email}' already exists")

    user = User(
        organization_id=organization_id,
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        auth_method=AuthMethod.LOCAL,
        is_active=True,
        is_admin=payload.is_admin,
    )
    session.add(user)
    await session.flush()
    return user


async def update_user(
    session: AsyncSession,
    organization_id: UUID,
    user_id: UUID,
    payload: UserUpdate,
) -> User:
    user = await get_user(session, organization_id, user_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    await session.flush()
    return user


async def reset_password(
    session: AsyncSession,
    organization_id: UUID,
    user_id: UUID,
    new_password: str,
) -> None:
    user = await get_user(session, organization_id, user_id)
    user.password_hash = hash_password(new_password)
    await session.flush()


# ---------------- role assignments ----------------


async def list_assignments(
    session: AsyncSession, organization_id: UUID, user_id: UUID
) -> list[tuple[RoleAssignment, str, str | None]]:
    """Return (assignment, role_name, scope_label)."""
    await get_user(session, organization_id, user_id)
    stmt = (
        select(RoleAssignment)
        .where(RoleAssignment.user_id == user_id)
        .options(selectinload(RoleAssignment.role))
        .order_by(RoleAssignment.created_at)
    )
    rows = list((await session.execute(stmt)).scalars())

    out: list[tuple[RoleAssignment, str, str | None]] = []
    for a in rows:
        label = await _resolve_scope_label(session, a.scope_type, a.scope_id)
        out.append((a, a.role.name, label))
    return out


async def create_assignment(
    session: AsyncSession,
    organization_id: UUID,
    user_id: UUID,
    payload: AssignmentCreate,
) -> RoleAssignment:
    user = await get_user(session, organization_id, user_id)

    role = (
        await session.execute(
            select(Role).where(Role.id == payload.role_id, Role.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if role is None:
        raise RoleNotInOrganization("role does not belong to this organization")

    # Validate scope_id matches scope_type
    if payload.scope_type == AssignmentScope.ORGANIZATION:
        scope_id = None
    elif payload.scope_type == AssignmentScope.SITE:
        if payload.scope_id is None:
            raise InvalidScope("scope_id is required for SITE scope")
        ok = (
            await session.execute(
                select(Site.id).where(
                    Site.id == payload.scope_id, Site.organization_id == organization_id
                )
            )
        ).first()
        if ok is None:
            raise InvalidScope("site not found in this organization")
        scope_id = payload.scope_id
    elif payload.scope_type == AssignmentScope.DEVICE:
        if payload.scope_id is None:
            raise InvalidScope("scope_id is required for DEVICE scope")
        ok = (
            await session.execute(
                select(Device.id).where(
                    Device.id == payload.scope_id, Device.organization_id == organization_id
                )
            )
        ).first()
        if ok is None:
            raise InvalidScope("device not found in this organization")
        scope_id = payload.scope_id
    else:
        raise InvalidScope(f"unknown scope_type {payload.scope_type}")

    assignment = RoleAssignment(
        user_id=user.id,
        role_id=role.id,
        scope_type=payload.scope_type,
        scope_id=scope_id,
    )
    session.add(assignment)
    await session.flush()
    return assignment


async def delete_assignment(
    session: AsyncSession,
    organization_id: UUID,
    user_id: UUID,
    assignment_id: UUID,
) -> None:
    user = await get_user(session, organization_id, user_id)
    assignment = (
        await session.execute(
            select(RoleAssignment).where(
                RoleAssignment.id == assignment_id, RoleAssignment.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise AssignmentNotFound("role assignment not found")
    await session.delete(assignment)
    await session.flush()


async def _resolve_scope_label(
    session: AsyncSession, scope_type: AssignmentScope, scope_id: UUID | None
) -> str | None:
    if scope_type == AssignmentScope.ORGANIZATION:
        return None
    if scope_id is None:
        return None
    if scope_type == AssignmentScope.SITE:
        site = (await session.execute(select(Site.name).where(Site.id == scope_id))).scalar_one_or_none()
        return site
    if scope_type == AssignmentScope.DEVICE:
        device = (
            await session.execute(select(Device.name).where(Device.id == scope_id))
        ).scalar_one_or_none()
        return device
    return None
