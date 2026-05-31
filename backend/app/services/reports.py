"""Report aggregations over audit_log + secret_reveals + secret_rotations.

The reports are pure read-only queries — never mutate state. CSV
serialization lives in the API layer; this module returns plain
dataclass-like rows.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.models.audit_log import AuditLog, AuditOutcome
from app.models.device import Device
from app.models.role import AssignmentScope, Role, RoleAssignment
from app.models.secret_audit import SecretReveal, SecretRotation
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.user import User

# Hard caps to keep response sizes sane; CSV downloads can be larger
# but the JSON UI view truncates so the browser stays responsive.
ROW_CAP = 5000


# Sections that count as "writes" for summary purposes. The audit_log
# uses these action verbs; anything else is a read.
WRITE_ACTIONS: set[str] = {
    "create",
    "update",
    "delete",
    "reset_password",
    "set_disabled",
    "rotate",
    "trigger",
    "manual",
    "bulk_reset_password",
    "assign_role",
    "revoke_role",
    "test_connection",
}


# ---------------- User activity ----------------


async def user_activity(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID | None,
    ts_from: datetime,
    ts_to: datetime,
    limit: int = ROW_CAP,
) -> tuple[list[dict], list[dict], bool]:
    """Return (rows, summary, truncated)."""
    filters = [
        AuditLog.organization_id == organization_id,
        AuditLog.ts >= ts_from,
        AuditLog.ts <= ts_to,
    ]
    if user_id:
        filters.append(AuditLog.user_id == user_id)

    stmt = (
        select(
            AuditLog,
            User.email,
            Device.name.label("device_name"),
            Site.name.label("site_name"),
            Tenant.name.label("tenant_name"),
        )
        .outerjoin(User, User.id == AuditLog.user_id)
        .outerjoin(Device, Device.id == AuditLog.device_id)
        .outerjoin(Site, Site.id == AuditLog.site_id)
        .outerjoin(Tenant, Tenant.id == Site.tenant_id)
        .where(*filters)
        .order_by(AuditLog.ts.desc())
        .limit(limit + 1)
    )
    raw = (await session.execute(stmt)).all()
    truncated = len(raw) > limit
    raw = raw[:limit]

    rows = [
        {
            "ts": a.ts,
            "user_id": a.user_id,
            "user_email": email,
            "section": a.section,
            "action": a.action,
            "outcome": a.outcome,
            "device_id": a.device_id,
            "device_name": dname,
            "site_id": a.site_id,
            "site_name": sname,
            "tenant_name": tname,
            "ip_address": a.ip_address,
        }
        for (a, email, dname, sname, tname) in raw
    ]

    summary_stmt = (
        select(
            AuditLog.user_id,
            User.email,
            func.count(AuditLog.id).label("total"),
            func.count(AuditLog.id).filter(
                AuditLog.action.in_(WRITE_ACTIONS)
            ).label("writes"),
            func.count(AuditLog.id)
            .filter(AuditLog.outcome != AuditOutcome.OK)
            .label("failures"),
            func.count(func.distinct(AuditLog.section)).label("sections"),
            func.count(func.distinct(AuditLog.device_id)).label("devices"),
        )
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(*filters)
        .group_by(AuditLog.user_id, User.email)
        .order_by(func.count(AuditLog.id).desc())
    )
    summary_rows = (await session.execute(summary_stmt)).all()
    summary = [
        {
            "user_id": uid,
            "user_email": email,
            "total": int(total),
            "writes": int(writes),
            "failures": int(failures),
            "sections_touched": int(sections),
            "devices_touched": int(devices),
        }
        for (uid, email, total, writes, failures, sections, devices) in summary_rows
    ]

    return rows, summary, truncated


# ---------------- Device activity ----------------


async def device_activity(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device_id: UUID,
    ts_from: datetime,
    ts_to: datetime,
    limit: int = ROW_CAP,
) -> tuple[str | None, list[dict], bool]:
    """Return (device_name, rows, truncated)."""
    device_name = (
        await session.execute(
            select(Device.name).where(
                Device.id == device_id, Device.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()

    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(
            AuditLog.organization_id == organization_id,
            AuditLog.device_id == device_id,
            AuditLog.ts >= ts_from,
            AuditLog.ts <= ts_to,
        )
        .order_by(AuditLog.ts.desc())
        .limit(limit + 1)
    )
    raw = (await session.execute(stmt)).all()
    truncated = len(raw) > limit
    raw = raw[:limit]

    rows = [
        {
            "ts": a.ts,
            "user_email": email,
            "section": a.section,
            "action": a.action,
            "outcome": a.outcome,
            "ip_address": a.ip_address,
            "request_payload": a.request_payload,
            "error_message": a.error_message,
        }
        for (a, email) in raw
    ]
    return device_name, rows, truncated


# ---------------- Secret access ----------------


async def secret_access(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID | None,
    ts_from: datetime,
    ts_to: datetime,
    limit: int = ROW_CAP,
) -> tuple[list[dict], int]:
    filters = [
        SecretReveal.organization_id == organization_id,
        SecretReveal.ts >= ts_from,
        SecretReveal.ts <= ts_to,
    ]
    if user_id:
        filters.append(SecretReveal.user_id == user_id)

    # Per (device, kind, identifier), the most recent rotation timestamp.
    rotation_subq = (
        select(
            SecretRotation.device_id,
            SecretRotation.secret_kind,
            SecretRotation.secret_identifier,
            func.max(SecretRotation.ts).label("last_rotation_ts"),
        )
        .where(SecretRotation.organization_id == organization_id)
        .group_by(
            SecretRotation.device_id,
            SecretRotation.secret_kind,
            SecretRotation.secret_identifier,
        )
        .subquery()
    )

    stmt = (
        select(
            SecretReveal,
            User.email,
            Device.name.label("device_name"),
            rotation_subq.c.last_rotation_ts,
        )
        .outerjoin(User, User.id == SecretReveal.user_id)
        .outerjoin(Device, Device.id == SecretReveal.device_id)
        .outerjoin(
            rotation_subq,
            (rotation_subq.c.device_id == SecretReveal.device_id)
            & (rotation_subq.c.secret_kind == SecretReveal.secret_kind)
            & (rotation_subq.c.secret_identifier == SecretReveal.secret_identifier),
        )
        .where(*filters)
        .order_by(SecretReveal.ts.desc())
        .limit(limit + 1)
    )
    raw = (await session.execute(stmt)).all()
    truncated = len(raw) > limit
    raw = raw[:limit]

    rows: list[dict] = []
    unrotated = 0
    for sr, email, dname, last_rotation in raw:
        rotated_since = last_rotation is not None and last_rotation > sr.ts
        if not rotated_since:
            unrotated += 1
        rows.append(
            {
                "ts": sr.ts,
                "user_email": email,
                "device_id": sr.device_id,
                "device_name": dname,
                "secret_kind": sr.secret_kind,
                "secret_identifier": sr.secret_identifier,
                "secret_label": sr.secret_label,
                "last_rotation_ts": last_rotation,
                "rotated_since_reveal": rotated_since,
                "ip_address": sr.ip_address,
                "justification": sr.justification,
            }
        )

    return rows, unrotated


# ---------------- Change report ----------------


async def changes(
    session: AsyncSession,
    *,
    organization_id: UUID,
    ts_from: datetime,
    ts_to: datetime,
    section: str | None,
    limit: int = ROW_CAP,
) -> tuple[list[dict], dict[str, int], dict[str, int], bool]:
    filters = [
        AuditLog.organization_id == organization_id,
        AuditLog.ts >= ts_from,
        AuditLog.ts <= ts_to,
        AuditLog.action.in_(WRITE_ACTIONS),
    ]
    if section:
        filters.append(AuditLog.section == section)

    stmt = (
        select(AuditLog, User.email, Device.name.label("device_name"))
        .outerjoin(User, User.id == AuditLog.user_id)
        .outerjoin(Device, Device.id == AuditLog.device_id)
        .where(*filters)
        .order_by(AuditLog.ts.desc())
        .limit(limit + 1)
    )
    raw = (await session.execute(stmt)).all()
    truncated = len(raw) > limit
    raw = raw[:limit]

    rows = [
        {
            "ts": a.ts,
            "user_email": email,
            "section": a.section,
            "action": a.action,
            "outcome": a.outcome,
            "device_id": a.device_id,
            "device_name": dname,
            "request_payload": a.request_payload,
        }
        for (a, email, dname) in raw
    ]
    by_section = dict(Counter(r["section"] for r in rows))
    by_user = dict(Counter(r["user_email"] or "(system)" for r in rows))
    return rows, by_section, by_user, truncated


# ---------------- User & roles report ----------------


async def user_roles_report(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> tuple[list[dict], list[dict]]:
    """For every user in the org, list their role assignments + scope
    labels. Also returns the role catalogue with permission strings so
    the UI can render side-by-side comparisons.

    Returns (user_rows, role_rows) — both as plain dicts so the API
    layer can flow them straight into the pydantic schemas."""
    users = list(
        (
            await session.execute(
                select(User).where(User.organization_id == organization_id)
            )
        ).scalars()
    )

    assignments = list(
        (
            await session.execute(
                select(RoleAssignment)
                .join(Role, RoleAssignment.role_id == Role.id)
                .where(Role.organization_id == organization_id)
                .options(selectinload(RoleAssignment.role))
            )
        ).scalars()
    )

    roles = list(
        (
            await session.execute(
                select(Role)
                .where(Role.organization_id == organization_id)
                .options(selectinload(Role.permissions))
            )
        ).scalars()
    )

    # Label lookups — same approach as access service. Cheap one-pass.
    tenant_labels = {
        t[0]: t[1]
        for t in (
            await session.execute(
                select(Tenant.id, Tenant.name).where(
                    Tenant.organization_id == organization_id
                )
            )
        ).all()
    }
    site_labels = {
        s[0]: s[1]
        for s in (
            await session.execute(
                select(Site.id, Site.name).where(
                    Site.organization_id == organization_id
                )
            )
        ).all()
    }
    device_labels = {
        d[0]: d[1]
        for d in (
            await session.execute(
                select(Device.id, Device.name).where(
                    Device.organization_id == organization_id
                )
            )
        ).all()
    }

    def _scope_label(stype: AssignmentScope, sid: UUID | None) -> str | None:
        if stype == AssignmentScope.ORGANIZATION:
            return "organization"
        if sid is None:
            return None
        if stype == AssignmentScope.TENANT:
            return tenant_labels.get(sid)
        if stype == AssignmentScope.SITE:
            return site_labels.get(sid)
        if stype == AssignmentScope.DEVICE:
            return device_labels.get(sid)
        return None

    by_user: dict[UUID, list[dict]] = {}
    role_user_count: dict[UUID, set[UUID]] = {}
    for a in assignments:
        by_user.setdefault(a.user_id, []).append(
            {
                "role_id": a.role_id,
                "role_name": a.role.name if a.role else "(deleted)",
                "scope_type": a.scope_type.value,
                "scope_id": a.scope_id,
                "scope_label": _scope_label(a.scope_type, a.scope_id),
            }
        )
        role_user_count.setdefault(a.role_id, set()).add(a.user_id)

    user_rows = []
    for u in users:
        my_assignments = by_user.get(u.id, [])
        permission_count = sum(
            len({(p.section, p.action.value) for p in r.permissions})
            for r in roles
            if r.id in {a["role_id"] for a in my_assignments}
        )
        user_rows.append(
            {
                "user_id": u.id,
                "email": u.email,
                "display_name": u.display_name,
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "totp_enrolled": u.totp_enrolled,
                "otp_login_enabled": u.otp_login_enabled,
                "assignments": my_assignments,
                "permission_count": permission_count,
            }
        )
    user_rows.sort(key=lambda r: (r["display_name"] or r["email"]).lower())

    role_rows = []
    for r in sorted(roles, key=lambda x: x.name.lower()):
        role_rows.append(
            {
                "role_id": r.id,
                "role_name": r.name,
                "is_system": r.is_system,
                "description": r.description,
                "user_count": len(role_user_count.get(r.id, set())),
                "permissions": sorted(
                    f"{p.section}:{p.action.value}" for p in r.permissions
                ),
            }
        )
    return user_rows, role_rows
