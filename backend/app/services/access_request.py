"""Request-Access workflow service.

Three responsibilities:
  - create / list / cancel access requests
  - approve / deny (admin only) and mint the resulting RoleAssignments
  - notify both sides via SMTP

The directory feed (every tenant/site/device the org owns, plus a
``has_access`` flag derived from the RBAC walker) sits next to it
because it's the surface the "Request access" buttons hang off of.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.access_request import (
    AccessRequest,
    AccessRequestGrant,
    AccessRequestStatus,
)
from app.models.audit_log import AuditOutcome
from app.models.device import Device
from app.models.organization import Organization
from app.models.role import AssignmentScope, Role, RoleAssignment
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.user import User
from app.services import audit as audit_svc
from app.services import email as email_svc
from app.services import rbac as rbac_svc

log = structlog.get_logger(__name__)


class AccessRequestError(Exception):
    """Generic exception. The API layer maps to 4xx based on context."""


class AccessRequestNotFound(AccessRequestError):
    pass


class AccessRequestForbidden(AccessRequestError):
    pass


class AccessRequestAlreadyDecided(AccessRequestError):
    pass


# ---------------- Create ----------------


async def create_request(
    session: AsyncSession,
    *,
    requester: User,
    scope_type: AssignmentScope,
    scope_id: UUID,
    reason: str | None,
) -> AccessRequest:
    if scope_type == AssignmentScope.ORGANIZATION:
        raise AccessRequestError("Organisation-wide grants must be made by an admin directly")

    # Validate the target exists in the requester's org.
    label = await _resolve_target_label(
        session, requester.organization_id, scope_type, scope_id
    )
    if label is None:
        raise AccessRequestError("target not found in this organization")

    # Don't allow piling up duplicate pending requests for the same target.
    existing = (
        await session.execute(
            select(AccessRequest).where(
                AccessRequest.requester_user_id == requester.id,
                AccessRequest.scope_type == scope_type,
                AccessRequest.scope_id == scope_id,
                AccessRequest.status == AccessRequestStatus.PENDING,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    req = AccessRequest(
        organization_id=requester.organization_id,
        requester_user_id=requester.id,
        scope_type=scope_type,
        scope_id=scope_id,
        reason=reason,
        status=AccessRequestStatus.PENDING,
    )
    session.add(req)
    await session.flush()
    return req


# ---------------- List ----------------


async def list_requests(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor: User,
    status: AccessRequestStatus | None = None,
) -> list[AccessRequest]:
    """Admins see all requests in the org; non-admins see their own."""
    stmt = (
        select(AccessRequest)
        .where(AccessRequest.organization_id == organization_id)
        .options(selectinload(AccessRequest.grants))
        .order_by(AccessRequest.created_at.desc())
    )
    if not actor.is_admin:
        stmt = stmt.where(AccessRequest.requester_user_id == actor.id)
    if status is not None:
        stmt = stmt.where(AccessRequest.status == status)
    return list((await session.execute(stmt)).scalars())


async def get_request(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor: User,
    request_id: UUID,
) -> AccessRequest:
    stmt = (
        select(AccessRequest)
        .where(
            AccessRequest.id == request_id,
            AccessRequest.organization_id == organization_id,
        )
        .options(selectinload(AccessRequest.grants))
    )
    req = (await session.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise AccessRequestNotFound("access request not found")
    if not actor.is_admin and req.requester_user_id != actor.id:
        raise AccessRequestForbidden("not your access request")
    return req


# ---------------- Decisions ----------------


async def approve_request(
    session: AsyncSession,
    *,
    request_id: UUID,
    actor: User,
    role_ids: list[UUID],
    expires_at: datetime | None,
    note: str | None,
) -> AccessRequest:
    if not actor.is_admin:
        raise AccessRequestForbidden("admin only")

    req = (
        await session.execute(
            select(AccessRequest).where(
                AccessRequest.id == request_id,
                AccessRequest.organization_id == actor.organization_id,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise AccessRequestNotFound("access request not found")
    if req.status != AccessRequestStatus.PENDING:
        raise AccessRequestAlreadyDecided(f"already {req.status.value}")

    roles = list(
        (
            await session.execute(
                select(Role).where(
                    Role.id.in_(role_ids),
                    Role.organization_id == actor.organization_id,
                )
            )
        ).scalars()
    )
    found_ids = {r.id for r in roles}
    missing = [r for r in role_ids if r not in found_ids]
    if missing:
        raise AccessRequestError(f"role(s) not in organisation: {missing}")

    # Skip role × scope rows the requester already has — keeps approvals
    # idempotent if an admin partially granted earlier.
    existing = {
        (a.role_id, a.scope_type, a.scope_id)
        for a in (
            await session.execute(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == req.requester_user_id,
                    RoleAssignment.role_id.in_(found_ids),
                )
            )
        ).scalars()
    }

    new_grants: list[AccessRequestGrant] = []
    for role in roles:
        if (role.id, req.scope_type, req.scope_id) in existing:
            continue
        assignment = RoleAssignment(
            user_id=req.requester_user_id,
            role_id=role.id,
            scope_type=req.scope_type,
            scope_id=req.scope_id,
            expires_at=expires_at,
        )
        session.add(assignment)
        await session.flush()
        new_grants.append(
            AccessRequestGrant(
                access_request_id=req.id,
                role_assignment_id=assignment.id,
            )
        )
    if new_grants:
        session.add_all(new_grants)

    req.status = AccessRequestStatus.APPROVED
    req.decided_at = datetime.now(UTC)
    req.decided_by_user_id = actor.id
    req.granted_expires_at = expires_at
    req.decision_note = note
    await session.flush()

    # Best-effort notification email; audit + DB state are durable.
    await _notify_decision(session, req, actor, approved=True)
    await audit_svc.write_audit(
        session,
        user_id=actor.id,
        organization_id=actor.organization_id,
        section="users",
        action="access_request_approve",
        outcome=AuditOutcome.OK,
        request_payload={
            "request_id": str(req.id),
            "role_ids": [str(r) for r in role_ids],
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )
    return req


async def deny_request(
    session: AsyncSession,
    *,
    request_id: UUID,
    actor: User,
    note: str | None,
) -> AccessRequest:
    if not actor.is_admin:
        raise AccessRequestForbidden("admin only")

    req = (
        await session.execute(
            select(AccessRequest).where(
                AccessRequest.id == request_id,
                AccessRequest.organization_id == actor.organization_id,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise AccessRequestNotFound("access request not found")
    if req.status != AccessRequestStatus.PENDING:
        raise AccessRequestAlreadyDecided(f"already {req.status.value}")

    req.status = AccessRequestStatus.DENIED
    req.decided_at = datetime.now(UTC)
    req.decided_by_user_id = actor.id
    req.decision_note = note
    await session.flush()
    await _notify_decision(session, req, actor, approved=False)
    await audit_svc.write_audit(
        session,
        user_id=actor.id,
        organization_id=actor.organization_id,
        section="users",
        action="access_request_deny",
        outcome=AuditOutcome.OK,
        request_payload={"request_id": str(req.id), "note": note},
    )
    return req


async def cancel_request(
    session: AsyncSession,
    *,
    request_id: UUID,
    actor: User,
) -> AccessRequest:
    req = (
        await session.execute(
            select(AccessRequest).where(
                AccessRequest.id == request_id,
                AccessRequest.organization_id == actor.organization_id,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise AccessRequestNotFound("access request not found")
    if req.requester_user_id != actor.id and not actor.is_admin:
        raise AccessRequestForbidden("not your access request")
    if req.status != AccessRequestStatus.PENDING:
        raise AccessRequestAlreadyDecided(f"already {req.status.value}")
    req.status = AccessRequestStatus.CANCELLED
    req.decided_at = datetime.now(UTC)
    req.decided_by_user_id = actor.id
    await session.flush()
    return req


# ---------------- Directory ----------------


async def directory(
    session: AsyncSession, *, actor: User
) -> list[dict]:
    """Return tenant → sites → devices with a per-node has_access flag.

    Implementation walks the RBAC resolver for each node. That's O(n)
    against the assignment list, which we read once and cache on the
    actor's session. Plenty fast for fleets in the hundreds — if a
    customer breaks that ceiling we can move to a single materialised
    join."""
    tenants = list(
        (
            await session.execute(
                select(Tenant).where(Tenant.organization_id == actor.organization_id)
            )
        ).scalars()
    )
    sites = list(
        (
            await session.execute(
                select(Site).where(Site.organization_id == actor.organization_id)
            )
        ).scalars()
    )
    devices = list(
        (
            await session.execute(
                select(Device).where(Device.organization_id == actor.organization_id)
            )
        ).scalars()
    )

    sites_by_tenant: dict[UUID, list[Site]] = {}
    for s in sites:
        sites_by_tenant.setdefault(s.tenant_id, []).append(s)
    devices_by_site: dict[UUID, list[Device]] = {}
    for d in devices:
        devices_by_site.setdefault(d.site_id, []).append(d)

    out: list[dict] = []
    for t in sorted(tenants, key=lambda x: x.name.lower()):
        t_has = await rbac_svc.can(
            session, actor, "tenants", "read", tenant_id=t.id
        )
        t_sites: list[dict] = []
        for s in sorted(sites_by_tenant.get(t.id, []), key=lambda x: x.name.lower()):
            s_has = await rbac_svc.can(
                session, actor, "sites", "read", site_id=s.id, tenant_id=t.id
            )
            s_devices: list[dict] = []
            for d in sorted(
                devices_by_site.get(s.id, []), key=lambda x: x.name.lower()
            ):
                d_has = await rbac_svc.can(
                    session,
                    actor,
                    "devices",
                    "read",
                    device_id=d.id,
                    site_id=s.id,
                    tenant_id=t.id,
                )
                s_devices.append(
                    {"id": d.id, "name": d.name, "has_access": d_has}
                )
            t_sites.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "has_access": s_has,
                    "devices": s_devices,
                }
            )
        out.append(
            {
                "id": t.id,
                "name": t.name,
                "has_access": t_has,
                "sites": t_sites,
            }
        )
    return out


# ---------------- Notifications ----------------


async def _notify_decision(
    session: AsyncSession,
    req: AccessRequest,
    decider: User,
    *,
    approved: bool,
) -> None:
    """Email the requester. SMTP is best-effort — the persisted state
    is the source of truth."""
    requester = (
        await session.execute(
            select(User).where(User.id == req.requester_user_id)
        )
    ).scalar_one_or_none()
    if requester is None:
        return
    org = (
        await session.execute(
            select(Organization).where(Organization.id == req.organization_id)
        )
    ).scalar_one()
    target_label = await _resolve_target_label(
        session, req.organization_id, req.scope_type, req.scope_id
    ) or "(target removed)"

    verdict = "approved" if approved else "denied"
    body = (
        f"Hi,\n\n"
        f"Your NetFleet access request for {req.scope_type.value} "
        f'"{target_label}" was {verdict} by {decider.email}.\n'
    )
    if req.granted_expires_at and approved:
        body += f"Access expires: {req.granted_expires_at.isoformat()}\n"
    if req.decision_note:
        body += f"\nAdmin note:\n{req.decision_note}\n"
    body += "\nSign in to NetFleet to use the new access.\n"
    try:
        await email_svc.send_email(
            org,
            to=requester.email,
            subject=f"NetFleet access request {verdict}",
            body_text=body,
        )
    except (email_svc.SmtpNotConfigured, email_svc.SmtpSendError) as e:
        log.warning(
            "access_request.decision_email_failed",
            request_id=str(req.id),
            error=str(e),
        )


async def notify_new_request(
    session: AsyncSession, req: AccessRequest
) -> None:
    """Notify every super-admin in the org. Called after create_request
    + commit so the email doesn't fire when the DB rolls back."""
    admins = list(
        (
            await session.execute(
                select(User).where(
                    User.organization_id == req.organization_id,
                    User.is_admin.is_(True),
                    User.is_active.is_(True),
                )
            )
        ).scalars()
    )
    if not admins:
        return
    org = (
        await session.execute(
            select(Organization).where(Organization.id == req.organization_id)
        )
    ).scalar_one()
    requester = (
        await session.execute(
            select(User).where(User.id == req.requester_user_id)
        )
    ).scalar_one_or_none()
    target_label = await _resolve_target_label(
        session, req.organization_id, req.scope_type, req.scope_id
    ) or "(target removed)"

    body_text = (
        f"Hi,\n\n"
        f"A NetFleet access request needs your attention.\n\n"
        f"From: {requester.email if requester else 'unknown'}\n"
        f"Target: {req.scope_type.value} '{target_label}'\n"
    )
    if req.reason:
        body_text += f"Reason: {req.reason}\n"
    body_text += (
        "\nReview it in the dashboard: /dashboard/access-requests/"
        + str(req.id)
        + "\n"
    )

    for admin in admins:
        try:
            await email_svc.send_email(
                org,
                to=admin.email,
                subject="NetFleet access request pending review",
                body_text=body_text,
            )
        except (email_svc.SmtpNotConfigured, email_svc.SmtpSendError) as e:
            log.warning(
                "access_request.new_email_failed",
                admin_id=str(admin.id),
                error=str(e),
            )


# ---------------- helpers ----------------


async def _resolve_target_label(
    session: AsyncSession,
    organization_id: UUID,
    scope_type: AssignmentScope,
    scope_id: UUID | None,
) -> str | None:
    if scope_id is None:
        return None
    if scope_type == AssignmentScope.TENANT:
        row = (
            await session.execute(
                select(Tenant.name).where(
                    Tenant.id == scope_id,
                    Tenant.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        return row
    if scope_type == AssignmentScope.SITE:
        row = (
            await session.execute(
                select(Site.name).where(
                    Site.id == scope_id,
                    Site.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        return row
    if scope_type == AssignmentScope.DEVICE:
        row = (
            await session.execute(
                select(Device.name).where(
                    Device.id == scope_id,
                    Device.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        return row
    return None
