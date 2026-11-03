"""RBAC enforcer — direct, transparent permission checks.

Each request asks: "Can this user perform <section, action> in the context of
<site_id or device_id>?". We resolve it by:

  1. Super-admin (`User.is_admin=True`) bypasses everything.
  2. Otherwise we walk the user's role assignments; for each whose scope
     contains the requested resource, we check if the role has a permission
     row matching the (section, action) — wildcard "*" allowed for either field.

This keeps policy in plain SQL rows you can inspect and `git diff`, with no
abstract policy DSL to debug. If we ever need fancier policies (time-of-day,
ABAC), we can swap in Casbin behind this function without changing call-sites.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.device import Device
from app.models.role import AssignmentScope, Permission, Role, RoleAssignment
from app.models.site import Site
from app.models.user import User

log = structlog.get_logger(__name__)


# ---------------- Section catalog ----------------
#
# "Application" sections — what the platform itself controls.
APP_SECTIONS: dict[str, list[str]] = {
    "tenants": ["read", "write"],
    "sites": ["read", "write"],
    "devices": ["read", "write", "execute"],   # execute = test_connection / reboot
    "users": ["read", "write"],
    "roles": ["read", "write"],
    "pkg.manager": ["read", "write", "execute"],
    "audit": ["read"],
    "events": ["read", "write"],
    "settings": ["read", "write"],
}

# "Driver" sections — what the vendor drivers expose. Kept in sync with
# `app/drivers/base.py::Capability`. The UI uses /api/v1/sections to render
# the role-permission editor; this list is the source of truth.
DRIVER_SECTIONS: dict[str, list[str]] = {
    # System
    "system.info":              ["read"],
    "system.reboot":            ["execute"],
    "system.backup":            ["read", "execute"],
    "system.user":              ["read", "write"],
    # IP
    "interface.list":           ["read", "write"],
    "ip.address":               ["read", "write"],
    "ip.route":                 ["read", "write"],
    "ip.service":               ["read", "write"],
    "ip.neighbor":              ["read", "write"],
    # DHCP
    "dhcp.server":              ["read", "write"],
    "dhcp.lease":               ["read", "write"],
    # Firewall
    "firewall.filter":          ["read", "write"],
    "firewall.nat":             ["read", "write"],
    "firewall.mangle":          ["read", "write"],
    # execute = enable/disable the firewall itself, which is a bigger hammer
    # than editing a rule and is worth being able to grant separately.
    "firewall.ufw":             ["read", "write", "execute"],
    # QoS
    "queue.simple":             ["read", "write"],
    "queue.tree":               ["read", "write"],
    # PPP / VPN
    "ppp.secret":               ["read", "write"],
    "vpn.l2tp":                 ["read", "write"],
    "vpn.pptp":                 ["read", "write"],
    "vpn.ipsec":                ["read", "write"],
    "vpn.sstp":                 ["read", "write"],
    "vpn.ovpn":                 ["read", "write"],
    "vpn.wireguard.interface":  ["read", "write"],
    "vpn.wireguard.peer":       ["read", "write"],
    # Tooling
    "tool.ping":                ["execute"],
    "tool.traceroute":          ["execute"],
    # Firmware (check + upgrade)
    "system.firmware":          ["read", "execute"],
    # Secret reveal — guards endpoints that expose plaintext credentials
    "secret.reveal":            ["execute"],
}

ALL_SECTIONS: dict[str, list[str]] = {**APP_SECTIONS, **DRIVER_SECTIONS}


# ---------------- Core check ----------------


async def can(
    session: AsyncSession,
    user: User,
    section: str,
    action: str,
    *,
    device_id: UUID | None = None,
    site_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> bool:
    """Return True if the user is permitted to do (section, action) in scope."""
    if user.is_admin:
        return True

    # Walk the chain: device → site → tenant. Resolve missing rungs.
    if device_id is not None and site_id is None:
        site_id = await _site_for_device(session, device_id)
    if site_id is not None and tenant_id is None:
        tenant_id = await _tenant_for_site(session, site_id)

    stmt = (
        select(RoleAssignment)
        .where(RoleAssignment.user_id == user.id)
        .options(selectinload(RoleAssignment.role).selectinload(Role.permissions))
    )
    assignments = list((await session.execute(stmt)).scalars())

    now = datetime.now(UTC)
    for a in assignments:
        # Time-limited grants (P21 Stage 6) drop out of the policy
        # check past their expiry — no need for a cleanup sweep, the
        # row stays around for audit purposes.
        if a.expires_at is not None and a.expires_at <= now:
            continue
        if not _scope_matches(a, device_id=device_id, site_id=site_id, tenant_id=tenant_id):
            continue
        if _role_grants(a.role, section, action):
            return True

    return False


async def require(
    session: AsyncSession,
    user: User,
    section: str,
    action: str,
    *,
    device_id: UUID | None = None,
    site_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> None:
    """Permission check that raises PermissionError on denial — caller maps to 403."""
    if not await can(
        session,
        user,
        section,
        action,
        device_id=device_id,
        site_id=site_id,
        tenant_id=tenant_id,
    ):
        raise PermissionError(f"denied: {section}:{action}")


# ---------------- Visibility (fleet lists) ----------------


class Visibility:
    """Which tenants / sites / devices a user can see in fleet lists.

    `everything` is True for super-admins and for anyone holding any
    role at organization scope. Otherwise visibility follows the scopes of
    the user's (unexpired) role assignments: a tenant assignment shows the
    tenant and everything under it, a site assignment the site and its
    devices, a device assignment the device — plus the site and tenant it
    sits in, so it can be navigated to.
    """

    def __init__(self) -> None:
        self.everything = False
        self.tenant_ids: set[UUID] = set()
        self.site_ids: set[UUID] = set()
        self.device_ids: set[UUID] = set()

    def device(self, device_id: UUID, site_id: UUID, tenant_id: UUID | None) -> bool:
        return (
            self.everything
            or device_id in self.device_ids
            or site_id in self.site_ids
            or (tenant_id is not None and tenant_id in self.tenant_ids)
        )


async def visibility(session: AsyncSession, user: User) -> Visibility:
    v = Visibility()
    if user.is_admin:
        v.everything = True
        return v
    stmt = (
        select(RoleAssignment)
        .where(RoleAssignment.user_id == user.id)
        .options(selectinload(RoleAssignment.role).selectinload(Role.permissions))
    )
    now = datetime.now(UTC)
    for a in (await session.execute(stmt)).scalars():
        if a.expires_at is not None and a.expires_at <= now:
            continue
        if not a.role.permissions:
            continue
        if a.scope_type == AssignmentScope.ORGANIZATION:
            v.everything = True
            return v
        if a.scope_type == AssignmentScope.TENANT and a.scope_id:
            v.tenant_ids.add(a.scope_id)
        elif a.scope_type == AssignmentScope.SITE and a.scope_id:
            v.site_ids.add(a.scope_id)
        elif a.scope_type == AssignmentScope.DEVICE and a.scope_id:
            v.device_ids.add(a.scope_id)
    return v


async def visible_ids(
    session: AsyncSession, user: User
) -> tuple[set[UUID], set[UUID], set[UUID]] | None:
    """(tenant_ids, site_ids, device_ids) the user may see, or None for all.

    Expands each assignment downward (tenant → its sites → their devices)
    and upward (a device's site and tenant, a site's tenant) so lists stay
    navigable without exposing siblings.
    """
    v = await visibility(session, user)
    if v.everything:
        return None
    tenants, sites, devices = set(v.tenant_ids), set(v.site_ids), set(v.device_ids)
    rows = (
        await session.execute(
            select(Device.id, Device.site_id, Site.tenant_id)
            .join(Site, Site.id == Device.site_id)
            .where(Device.organization_id == user.organization_id)
        )
    ).all()
    for dev_id, site_id, tenant_id in rows:
        if v.device(dev_id, site_id, tenant_id):
            devices.add(dev_id)
            sites.add(site_id)
            if tenant_id is not None:
                tenants.add(tenant_id)
    site_rows = (
        await session.execute(
            select(Site.id, Site.tenant_id).where(Site.organization_id == user.organization_id)
        )
    ).all()
    for site_id, tenant_id in site_rows:
        if tenant_id in v.tenant_ids:
            sites.add(site_id)
        if site_id in v.site_ids and tenant_id is not None:
            tenants.add(tenant_id)
    return tenants, sites, devices


# ---------------- helpers ----------------


def _scope_matches(
    assignment: RoleAssignment,
    *,
    device_id: UUID | None,
    site_id: UUID | None,
    tenant_id: UUID | None,
) -> bool:
    if assignment.scope_type == AssignmentScope.ORGANIZATION:
        return True
    if assignment.scope_type == AssignmentScope.TENANT:
        return tenant_id is not None and assignment.scope_id == tenant_id
    if assignment.scope_type == AssignmentScope.SITE:
        return site_id is not None and assignment.scope_id == site_id
    if assignment.scope_type == AssignmentScope.DEVICE:
        return device_id is not None and assignment.scope_id == device_id
    return False


def _role_grants(role: Role, section: str, action: str) -> bool:
    for p in role.permissions:
        if (p.section == section or p.section == "*") and (
            p.action == action or p.action == "*"
        ):
            return True
    return False


async def _site_for_device(session: AsyncSession, device_id: UUID) -> UUID | None:
    stmt = select(Device.site_id).where(Device.id == device_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _tenant_for_site(session: AsyncSession, site_id: UUID) -> UUID | None:
    stmt = select(Site.tenant_id).where(Site.id == site_id)
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------- System role bootstrap ----------------


async def seed_system_roles(session: AsyncSession, organization_id: UUID) -> None:
    """Idempotent — creates 'viewer' and 'operator' system roles if absent.

    The org's first admin (is_admin=True on the User row) bypasses RBAC entirely.
    System roles are pre-defined templates an MSP can hand out.
    """
    existing = {
        r.name
        for r in (
            await session.execute(
                select(Role).where(
                    Role.organization_id == organization_id, Role.is_system.is_(True)
                )
            )
        ).scalars()
    }

    if "viewer" not in existing:
        viewer = Role(
            organization_id=organization_id,
            name="viewer",
            description="Read-only access to all sections.",
            is_system=True,
        )
        session.add(viewer)
        await session.flush()
        for sec in ALL_SECTIONS:
            session.add(Permission(role_id=viewer.id, section=sec, action="read"))

    if "operator" not in existing:
        operator = Role(
            organization_id=organization_id,
            name="operator",
            description="Read everything; write on operational sections (DHCP, NAT, queues).",
            is_system=True,
        )
        session.add(operator)
        await session.flush()
        for sec in ALL_SECTIONS:
            session.add(Permission(role_id=operator.id, section=sec, action="read"))
        for sec in ("dhcp.server", "dhcp.lease", "firewall.nat", "queue.simple", "ppp.secret"):
            session.add(Permission(role_id=operator.id, section=sec, action="write"))

    await session.flush()
