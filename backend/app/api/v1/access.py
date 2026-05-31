"""Access-resolver endpoints — drives the "who has access here?"
panels on tenant / site / device detail pages, and the per-user
access map in Reports.

Kept in a dedicated module instead of splitting between tenants.py,
sites.py and devices.py so the four endpoints share one schema import
and one auth posture.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import db_session, get_current_user, require_permission
from app.models.role import AssignmentScope
from app.models.user import User
from app.schemas.access import (
    AccessEntryPublic,
    AccessReportPublic,
    PermissionTuple,
    UserAccessDevicePublic,
    UserAccessMapPublic,
    UserAccessSitePublic,
    UserAccessTenantPublic,
    UserScopeGrantPublic,
)
from app.services import access as access_svc

router = APIRouter()


def _entry_to_public(e: access_svc.AccessEntry) -> AccessEntryPublic:
    data = asdict(e)
    if data["source_scope_type"] is not None:
        data["source_scope_type"] = data["source_scope_type"].value
    return AccessEntryPublic.model_validate(data)


def _grant_to_public(g: access_svc.UserScopeGrant) -> UserScopeGrantPublic:
    data = asdict(g)
    if data["via_scope_type"] is not None:
        data["via_scope_type"] = data["via_scope_type"].value
    return UserScopeGrantPublic.model_validate(data)


# ---------------- Who has access here ----------------


async def _who(
    scope_type: AssignmentScope,
    scope_id: UUID,
    user: User,
    session: AsyncSession,
) -> AccessReportPublic:
    report = await access_svc.who_has_access(
        session,
        organization_id=user.organization_id,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return AccessReportPublic(
        scope_type=report.scope_type.value,
        scope_id=report.scope_id,
        scope_label=report.scope_label,
        entries=[_entry_to_public(e) for e in report.entries],
    )


@router.get("/tenant/{tenant_id}", response_model=AccessReportPublic)
async def tenant_access(
    tenant_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AccessReportPublic:
    return await _who(AssignmentScope.TENANT, tenant_id, user, session)


@router.get("/site/{site_id}", response_model=AccessReportPublic)
async def site_access(
    site_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AccessReportPublic:
    return await _who(AssignmentScope.SITE, site_id, user, session)


@router.get("/device/{device_id}", response_model=AccessReportPublic)
async def device_access(
    device_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AccessReportPublic:
    return await _who(AssignmentScope.DEVICE, device_id, user, session)


# ---------------- Per-user access map ----------------


@router.get("/user/{user_id}", response_model=UserAccessMapPublic)
async def user_access(
    user_id: UUID,
    actor: User = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(db_session),
) -> UserAccessMapPublic:
    m = await access_svc.user_access_map(
        session, organization_id=actor.organization_id, user_id=user_id
    )
    if not m.tenants and not m.permissions:
        # Either the user is not in this org or genuinely has zero
        # grants. Caller distinguishes via the empty payload — 404 is
        # too coarse because zero-grants is a legit answer.
        pass

    tenants = [
        UserAccessTenantPublic(
            tenant_id=t.tenant_id,
            tenant_name=t.tenant_name,
            grants=[_grant_to_public(g) for g in t.grants],
            sites=[
                UserAccessSitePublic(
                    site_id=s.site_id,
                    site_name=s.site_name,
                    grants=[_grant_to_public(g) for g in s.grants],
                    devices=[
                        UserAccessDevicePublic(
                            device_id=d.device_id,
                            device_name=d.device_name,
                            grants=[_grant_to_public(g) for g in d.grants],
                        )
                        for d in s.devices
                    ],
                )
                for s in t.sites
            ],
        )
        for t in m.tenants
    ]
    return UserAccessMapPublic(
        user_id=m.user_id,
        tenants=tenants,
        permissions=[PermissionTuple(section=s, action=a) for s, a in m.permissions],
    )


# Guard against a typo-driven 404 — return 400 explicitly for bad UUIDs
# isn't needed here because FastAPI handles it before the dependency
# chain. We keep this comment for future maintainers wondering why no
# input validation lives in this module.
_ = status  # silence unused-import warning when status is referenced only via fastapi
