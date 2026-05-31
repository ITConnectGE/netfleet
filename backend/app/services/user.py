"""User + role-assignment service."""

from __future__ import annotations

import secrets
import string
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_password
from app.models.device import Device
from app.models.role import AssignmentScope, Role, RoleAssignment
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.user import AuthMethod, User
from app.schemas.user import (
    AssignmentBulkCreate,
    AssignmentCreate,
    UserCreate,
    UserUpdate,
)

# Character set for auto-generated invite passwords. We deliberately
# drop characters that are ambiguous in print (`0`, `O`, `1`, `l`, `I`,
# `|`) so the inviter can read the password to the invitee over the
# phone without spelling-bee theatrics.
_INVITE_PWD_ALPHABET = "".join(
    c for c in string.ascii_letters + string.digits if c not in "0O1lI|"
) + "@#$%^&*?+-_=:."
_INVITE_PWD_LENGTH = 16


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


def generate_invite_password() -> str:
    """Cryptographically-random password used when an admin chooses
    "auto-generate" on the invite form (or no password is supplied)."""
    return "".join(
        secrets.choice(_INVITE_PWD_ALPHABET) for _ in range(_INVITE_PWD_LENGTH)
    )


async def create_user(
    session: AsyncSession, organization_id: UUID, payload: UserCreate
) -> tuple[User, str | None]:
    """Create a user. Returns (user, generated_password). When the
    caller supplied a password, generated_password is None — the caller
    already has it. When it was auto-generated, the plaintext is
    returned exactly once so the API layer can surface it to the
    inviter; the password is never accessible again after that."""
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

    if payload.password:
        plaintext = payload.password
        generated: str | None = None
        must_change = False
    else:
        plaintext = generate_invite_password()
        generated = plaintext
        # Force the invitee to set their own password on first login;
        # admins shouldn't know an active password long-term.
        must_change = True

    mobile = _normalise_phone(payload.mobile_phone)

    user = User(
        organization_id=organization_id,
        email=email,
        display_name=payload.display_name,
        mobile_phone=mobile,
        password_hash=hash_password(plaintext),
        auth_method=AuthMethod.LOCAL,
        is_active=True,
        is_admin=payload.is_admin,
        must_change_password=must_change,
    )
    session.add(user)
    await session.flush()

    # Org-scope role assignments at invite time. Site/device scope is
    # configured later through /users/{id}/assignments; this is purely
    # the "give them this role across the whole org" shortcut.
    for role_id in payload.role_ids:
        role = (
            await session.execute(
                select(Role).where(
                    Role.id == role_id, Role.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()
        if role is None:
            raise RoleNotInOrganization(f"role {role_id} not in organisation")
        session.add(
            RoleAssignment(
                user_id=user.id,
                role_id=role.id,
                scope_type=AssignmentScope.ORGANIZATION,
                scope_id=None,
            )
        )
    await session.flush()
    return user, generated


async def update_user(
    session: AsyncSession,
    organization_id: UUID,
    user_id: UUID,
    payload: UserUpdate,
) -> User:
    user = await get_user(session, organization_id, user_id)
    data = payload.model_dump(exclude_unset=True)
    if "mobile_phone" in data:
        data["mobile_phone"] = _normalise_phone(data["mobile_phone"])
    for k, v in data.items():
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
    # Admin-initiated resets always require the target to set their
    # own password before continuing — same UX rule as invite.
    user.must_change_password = True
    await session.flush()


def _normalise_phone(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = "".join(c for c in raw if c.isdigit() or c == "+")
    return cleaned or None


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
    elif payload.scope_type == AssignmentScope.TENANT:
        if payload.scope_id is None:
            raise InvalidScope("scope_id is required for TENANT scope")
        ok = (
            await session.execute(
                select(Tenant.id).where(
                    Tenant.id == payload.scope_id, Tenant.organization_id == organization_id
                )
            )
        ).first()
        if ok is None:
            raise InvalidScope("tenant not found in this organization")
        scope_id = payload.scope_id
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


async def bulk_create_assignments(
    session: AsyncSession,
    organization_id: UUID,
    user_id: UUID,
    payload: AssignmentBulkCreate,
) -> tuple[list[RoleAssignment], int]:
    """Grant one role across many scopes. Skips scopes the user already
    has for this role. Returns (newly_created, skipped_existing_count)."""
    user = await get_user(session, organization_id, user_id)

    role = (
        await session.execute(
            select(Role).where(
                Role.id == payload.role_id, Role.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if role is None:
        raise RoleNotInOrganization("role does not belong to this organization")

    existing = {
        (a.scope_type, a.scope_id)
        for a in (
            await session.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.role_id == role.id,
                )
            )
        ).scalars()
    }

    created: list[RoleAssignment] = []
    skipped = 0
    for scope in payload.scopes:
        scope_id = await _validate_scope(
            session, organization_id, scope.scope_type, scope.scope_id
        )
        key = (scope.scope_type, scope_id)
        if key in existing:
            skipped += 1
            continue
        assignment = RoleAssignment(
            user_id=user.id,
            role_id=role.id,
            scope_type=scope.scope_type,
            scope_id=scope_id,
        )
        session.add(assignment)
        existing.add(key)
        created.append(assignment)
    await session.flush()
    return created, skipped


async def _validate_scope(
    session: AsyncSession,
    organization_id: UUID,
    scope_type: AssignmentScope,
    scope_id: UUID | None,
) -> UUID | None:
    """Mirror the per-scope validation logic from create_assignment but
    callable from the bulk path without re-creating the payload object."""
    if scope_type == AssignmentScope.ORGANIZATION:
        return None
    if scope_id is None:
        raise InvalidScope(f"scope_id is required for {scope_type} scope")
    if scope_type == AssignmentScope.TENANT:
        ok = (
            await session.execute(
                select(Tenant.id).where(
                    Tenant.id == scope_id, Tenant.organization_id == organization_id
                )
            )
        ).first()
        if ok is None:
            raise InvalidScope("tenant not found in this organization")
        return scope_id
    if scope_type == AssignmentScope.SITE:
        ok = (
            await session.execute(
                select(Site.id).where(
                    Site.id == scope_id, Site.organization_id == organization_id
                )
            )
        ).first()
        if ok is None:
            raise InvalidScope("site not found in this organization")
        return scope_id
    if scope_type == AssignmentScope.DEVICE:
        ok = (
            await session.execute(
                select(Device.id).where(
                    Device.id == scope_id, Device.organization_id == organization_id
                )
            )
        ).first()
        if ok is None:
            raise InvalidScope("device not found in this organization")
        return scope_id
    raise InvalidScope(f"unknown scope_type {scope_type}")


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
    if scope_type == AssignmentScope.TENANT:
        return (
            await session.execute(select(Tenant.name).where(Tenant.id == scope_id))
        ).scalar_one_or_none()
    if scope_type == AssignmentScope.SITE:
        return (
            await session.execute(select(Site.name).where(Site.id == scope_id))
        ).scalar_one_or_none()
    if scope_type == AssignmentScope.DEVICE:
        return (
            await session.execute(select(Device.name).where(Device.id == scope_id))
        ).scalar_one_or_none()
    return None
