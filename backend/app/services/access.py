"""Access-resolver service.

Two questions land here:

  - "Who can reach this tenant / site / device?"     → who_has_access()
  - "Where can this user reach inside the fleet?"    → user_access_map()

The data model is straightforward — RoleAssignment ties a (user, role)
to a scope (org / tenant / site / device). The inheritance walk is
what costs a few lines: an org-scope assignment covers every tenant,
site and device under the organisation; a tenant-scope assignment
covers every site and device under the tenant; etc.

The service is read-only and pure; the API layer wraps it with auth
checks. Mock-friendly because we hand in the AsyncSession and the
target IDs without touching globals.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.device import Device
from app.models.role import AssignmentScope, Role, RoleAssignment
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.user import User


# ---------------- Shapes ----------------


@dataclass(slots=True)
class AccessEntry:
    user_id: UUID
    email: str
    display_name: str | None
    is_admin: bool
    role_id: UUID | None  # None for super-admins (no role binding)
    role_name: str | None
    source_scope_type: AssignmentScope | None  # None for super-admins
    source_scope_id: UUID | None
    source_scope_label: str | None


@dataclass(slots=True)
class AccessReport:
    scope_type: AssignmentScope
    scope_id: UUID | None
    scope_label: str
    entries: list[AccessEntry]


# ---------------- who_has_access ----------------


async def who_has_access(
    session: AsyncSession,
    organization_id: UUID,
    *,
    scope_type: AssignmentScope,
    scope_id: UUID,
) -> AccessReport:
    """Return every user who can reach the target scope, with the role
    + originating assignment that grants it. Includes super-admins
    (they implicitly cover everything in the org)."""
    target_label, ancestor_tenant_id, ancestor_site_id = await _resolve_target(
        session, organization_id, scope_type, scope_id
    )

    # Pull every user in the org once. Cheap relative to walking the
    # assignment graph per user, and we need their identity fields
    # anyway.
    users = list(
        (
            await session.execute(
                select(User).where(User.organization_id == organization_id)
            )
        ).scalars()
    )
    users_by_id = {u.id: u for u in users}

    # All role assignments in the org touching any of these users, with
    # role eagerly loaded so we can show the role name without N+1.
    assignments = list(
        (
            await session.execute(
                select(RoleAssignment)
                .where(RoleAssignment.user_id.in_(list(users_by_id.keys())))
                .options(selectinload(RoleAssignment.role))
            )
        ).scalars()
    )

    # Label lookups for "this assignment came from tenant Foo" rendering.
    tenant_labels = await _label_map(session, Tenant, organization_id)
    site_labels = await _label_map(session, Site, organization_id)
    device_labels = await _label_map(session, Device, organization_id)

    entries: list[AccessEntry] = []
    for a in assignments:
        if not _assignment_covers(
            a,
            scope_type=scope_type,
            scope_id=scope_id,
            ancestor_tenant_id=ancestor_tenant_id,
            ancestor_site_id=ancestor_site_id,
        ):
            continue
        u = users_by_id.get(a.user_id)
        if u is None:
            continue
        entries.append(
            AccessEntry(
                user_id=u.id,
                email=u.email,
                display_name=u.display_name,
                is_admin=u.is_admin,
                role_id=a.role_id,
                role_name=a.role.name if a.role else None,
                source_scope_type=a.scope_type,
                source_scope_id=a.scope_id,
                source_scope_label=_scope_label(
                    a.scope_type,
                    a.scope_id,
                    tenant_labels,
                    site_labels,
                    device_labels,
                ),
            )
        )

    # Super-admins (User.is_admin=True) bypass RBAC entirely — list them
    # at the top so the operator sees who's holding the master key.
    for u in users:
        if u.is_admin:
            entries.insert(
                0,
                AccessEntry(
                    user_id=u.id,
                    email=u.email,
                    display_name=u.display_name,
                    is_admin=True,
                    role_id=None,
                    role_name=None,
                    source_scope_type=None,
                    source_scope_id=None,
                    source_scope_label="super-admin",
                ),
            )

    return AccessReport(
        scope_type=scope_type,
        scope_id=scope_id,
        scope_label=target_label,
        entries=entries,
    )


def _assignment_covers(
    a: RoleAssignment,
    *,
    scope_type: AssignmentScope,
    scope_id: UUID,
    ancestor_tenant_id: UUID | None,
    ancestor_site_id: UUID | None,
) -> bool:
    if a.scope_type == AssignmentScope.ORGANIZATION:
        return True
    if a.scope_type == AssignmentScope.TENANT:
        # Tenant-scope covers itself + sites + devices under it.
        return a.scope_id == ancestor_tenant_id or (
            scope_type == AssignmentScope.TENANT and a.scope_id == scope_id
        )
    if a.scope_type == AssignmentScope.SITE:
        # Site-scope covers itself + devices under it.
        return a.scope_id == ancestor_site_id or (
            scope_type == AssignmentScope.SITE and a.scope_id == scope_id
        )
    if a.scope_type == AssignmentScope.DEVICE:
        return scope_type == AssignmentScope.DEVICE and a.scope_id == scope_id
    return False


# ---------------- user_access_map ----------------


@dataclass(slots=True)
class UserScopeGrant:
    """One row in a user's access map. role_id can be None for the
    super-admin pseudo-grant."""

    role_id: UUID | None
    role_name: str | None
    via_scope_type: AssignmentScope | None
    via_scope_id: UUID | None
    via_scope_label: str | None


@dataclass(slots=True)
class UserAccessTenant:
    tenant_id: UUID
    tenant_name: str
    grants: list[UserScopeGrant]
    sites: list[UserAccessSite]


@dataclass(slots=True)
class UserAccessSite:
    site_id: UUID
    site_name: str
    grants: list[UserScopeGrant]
    devices: list[UserAccessDevice]


@dataclass(slots=True)
class UserAccessDevice:
    device_id: UUID
    device_name: str
    grants: list[UserScopeGrant]


@dataclass(slots=True)
class UserAccessMap:
    user_id: UUID
    tenants: list[UserAccessTenant]
    # Permissions matrix for quick rendering — list of (section, action)
    # tuples that the user effectively holds across the org. Doesn't try
    # to model scoping at this level; the per-scope detail above does.
    permissions: list[tuple[str, str]]


async def user_access_map(
    session: AsyncSession,
    organization_id: UUID,
    user_id: UUID,
) -> UserAccessMap:
    """Walk a user's assignments and stamp every tenant / site / device
    that they can reach with the role + scope chain that grants it."""
    user = (
        await session.execute(
            select(User).where(
                User.id == user_id, User.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if user is None:
        return UserAccessMap(user_id=user_id, tenants=[], permissions=[])

    tenants = list(
        (
            await session.execute(
                select(Tenant).where(Tenant.organization_id == organization_id)
            )
        ).scalars()
    )
    sites = list(
        (
            await session.execute(
                select(Site).where(Site.organization_id == organization_id)
            )
        ).scalars()
    )
    devices = list(
        (
            await session.execute(
                select(Device).where(Device.organization_id == organization_id)
            )
        ).scalars()
    )

    assignments = list(
        (
            await session.execute(
                select(RoleAssignment)
                .where(RoleAssignment.user_id == user_id)
                .options(selectinload(RoleAssignment.role).selectinload(Role.permissions))
            )
        ).scalars()
    )

    super_grant = (
        UserScopeGrant(
            role_id=None,
            role_name=None,
            via_scope_type=None,
            via_scope_id=None,
            via_scope_label="super-admin",
        )
        if user.is_admin
        else None
    )

    tenant_grants: dict[UUID, list[UserScopeGrant]] = defaultdict(list)
    site_grants: dict[UUID, list[UserScopeGrant]] = defaultdict(list)
    device_grants: dict[UUID, list[UserScopeGrant]] = defaultdict(list)
    org_grants: list[UserScopeGrant] = []

    tenant_labels = {t.id: t.name for t in tenants}
    site_labels = {s.id: s.name for s in sites}
    device_labels = {d.id: d.name for d in devices}

    for a in assignments:
        role_name = a.role.name if a.role else None
        grant_label = _scope_label(
            a.scope_type, a.scope_id, tenant_labels, site_labels, device_labels
        )
        grant = UserScopeGrant(
            role_id=a.role_id,
            role_name=role_name,
            via_scope_type=a.scope_type,
            via_scope_id=a.scope_id,
            via_scope_label=grant_label,
        )
        if a.scope_type == AssignmentScope.ORGANIZATION:
            org_grants.append(grant)
        elif a.scope_type == AssignmentScope.TENANT and a.scope_id is not None:
            tenant_grants[a.scope_id].append(grant)
        elif a.scope_type == AssignmentScope.SITE and a.scope_id is not None:
            site_grants[a.scope_id].append(grant)
        elif a.scope_type == AssignmentScope.DEVICE and a.scope_id is not None:
            device_grants[a.scope_id].append(grant)

    sites_by_tenant: dict[UUID, list[Site]] = defaultdict(list)
    for s in sites:
        sites_by_tenant[s.tenant_id].append(s)
    devices_by_site: dict[UUID, list[Device]] = defaultdict(list)
    for d in devices:
        devices_by_site[d.site_id].append(d)

    def _grants_for(level_grants: list[UserScopeGrant]) -> list[UserScopeGrant]:
        # Prepend the wider grants so the reader sees inheritance order.
        out: list[UserScopeGrant] = []
        if super_grant:
            out.append(super_grant)
        out.extend(org_grants)
        out.extend(level_grants)
        return out

    out_tenants: list[UserAccessTenant] = []
    for t in sorted(tenants, key=lambda x: x.name.lower()):
        t_grants = _grants_for(tenant_grants.get(t.id, []))
        out_sites: list[UserAccessSite] = []
        for s in sorted(sites_by_tenant.get(t.id, []), key=lambda x: x.name.lower()):
            s_grants_specific = list(t_grants) + site_grants.get(s.id, [])
            out_devices: list[UserAccessDevice] = []
            for d in sorted(
                devices_by_site.get(s.id, []), key=lambda x: x.name.lower()
            ):
                d_grants = list(s_grants_specific) + device_grants.get(d.id, [])
                if not d_grants:
                    continue
                out_devices.append(
                    UserAccessDevice(
                        device_id=d.id, device_name=d.name, grants=d_grants
                    )
                )
            if s_grants_specific or out_devices:
                out_sites.append(
                    UserAccessSite(
                        site_id=s.id,
                        site_name=s.name,
                        grants=s_grants_specific,
                        devices=out_devices,
                    )
                )
        if t_grants or out_sites:
            out_tenants.append(
                UserAccessTenant(
                    tenant_id=t.id,
                    tenant_name=t.name,
                    grants=t_grants,
                    sites=out_sites,
                )
            )

    # Effective permission tuples — union across roles touching this
    # user. Super-admin gets a synthetic wildcard so the UI can render
    # "everything".
    perms: set[tuple[str, str]] = set()
    if user.is_admin:
        perms.add(("*", "*"))
    for a in assignments:
        if a.role and a.role.permissions:
            for p in a.role.permissions:
                perms.add((p.section, p.action.value))

    return UserAccessMap(
        user_id=user_id,
        tenants=out_tenants,
        permissions=sorted(perms),
    )


# ---------------- helpers ----------------


async def _resolve_target(
    session: AsyncSession,
    organization_id: UUID,
    scope_type: AssignmentScope,
    scope_id: UUID,
) -> tuple[str, UUID | None, UUID | None]:
    """Return (display_label, ancestor_tenant_id, ancestor_site_id)
    for the target scope. Ancestor fields let the assignment-covers
    check skip walking the graph for every assignment."""
    if scope_type == AssignmentScope.TENANT:
        t = (
            await session.execute(
                select(Tenant).where(
                    Tenant.id == scope_id, Tenant.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()
        return (t.name if t else "—", scope_id, None)
    if scope_type == AssignmentScope.SITE:
        s = (
            await session.execute(
                select(Site).where(
                    Site.id == scope_id, Site.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()
        return (s.name if s else "—", s.tenant_id if s else None, scope_id)
    if scope_type == AssignmentScope.DEVICE:
        d = (
            await session.execute(
                select(Device).where(
                    Device.id == scope_id, Device.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()
        if d is None:
            return ("—", None, None)
        site = (
            await session.execute(select(Site).where(Site.id == d.site_id))
        ).scalar_one_or_none()
        return (
            d.name,
            site.tenant_id if site else None,
            site.id if site else None,
        )
    return ("organization", None, None)


async def _label_map(
    session: AsyncSession, model, organization_id: UUID
) -> dict[UUID, str]:
    rows = (
        await session.execute(
            select(model.id, model.name).where(model.organization_id == organization_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def _scope_label(
    scope_type: AssignmentScope,
    scope_id: UUID | None,
    tenant_labels: dict[UUID, str],
    site_labels: dict[UUID, str],
    device_labels: dict[UUID, str],
) -> str | None:
    if scope_type == AssignmentScope.ORGANIZATION:
        return "organization"
    if scope_id is None:
        return None
    if scope_type == AssignmentScope.TENANT:
        return tenant_labels.get(scope_id)
    if scope_type == AssignmentScope.SITE:
        return site_labels.get(scope_id)
    if scope_type == AssignmentScope.DEVICE:
        return device_labels.get(scope_id)
    return None
