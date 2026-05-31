"""Request-Access endpoints: create / list / decide / cancel."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import client_ip, db_session, get_current_user
from app.models.access_request import (
    AccessRequest,
    AccessRequestStatus,
)
from app.models.audit_log import AuditOutcome
from app.models.role import AssignmentScope, Role, RoleAssignment
from app.models.user import User
from app.schemas.access_request import (
    AccessRequestApprove,
    AccessRequestCreate,
    AccessRequestDeny,
    AccessRequestGrantPublic,
    AccessRequestPublic,
    DirectoryDevice,
    DirectoryReport,
    DirectorySite,
    DirectoryTenant,
)
from app.services import access_request as access_req_svc
from app.services import audit as audit_svc

router = APIRouter()


async def _to_public(
    session: AsyncSession, req: AccessRequest
) -> AccessRequestPublic:
    requester = (
        await session.execute(select(User).where(User.id == req.requester_user_id))
    ).scalar_one_or_none()
    decided_by = None
    if req.decided_by_user_id is not None:
        decided_by = (
            await session.execute(
                select(User).where(User.id == req.decided_by_user_id)
            )
        ).scalar_one_or_none()

    scope_label = await access_req_svc._resolve_target_label(  # noqa: SLF001
        session, req.organization_id, req.scope_type, req.scope_id
    )

    grant_pubs: list[AccessRequestGrantPublic] = []
    if req.grants:
        # Hydrate role + assignment data so the frontend can render each
        # produced binding inline.
        assignment_ids = [g.role_assignment_id for g in req.grants]
        assignments = list(
            (
                await session.execute(
                    select(RoleAssignment)
                    .where(RoleAssignment.id.in_(assignment_ids))
                    .options(selectinload(RoleAssignment.role))
                )
            ).scalars()
        )
        by_id = {a.id: a for a in assignments}
        for g in req.grants:
            a = by_id.get(g.role_assignment_id)
            if a is None or a.role is None:
                continue
            grant_pubs.append(
                AccessRequestGrantPublic(
                    role_id=a.role_id,
                    role_name=a.role.name,
                    assignment_id=a.id,
                    expires_at=a.expires_at,
                )
            )

    return AccessRequestPublic(
        id=req.id,
        organization_id=req.organization_id,
        requester_user_id=req.requester_user_id,
        requester_email=requester.email if requester else "unknown@local",
        requester_display_name=requester.display_name if requester else None,
        scope_type=req.scope_type.value,
        scope_id=req.scope_id,
        scope_label=scope_label,
        reason=req.reason,
        status=req.status.value,
        created_at=req.created_at,
        updated_at=req.updated_at,
        decided_at=req.decided_at,
        decided_by_user_id=req.decided_by_user_id,
        decided_by_email=decided_by.email if decided_by else None,
        granted_expires_at=req.granted_expires_at,
        decision_note=req.decision_note,
        grants=grant_pubs,
    )


# ---------------- Create / list / get ----------------


@router.post("", response_model=AccessRequestPublic, status_code=status.HTTP_201_CREATED)
async def create_access_request(
    payload: AccessRequestCreate,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AccessRequestPublic:
    try:
        req = await access_req_svc.create_request(
            session,
            requester=user,
            scope_type=AssignmentScope(payload.scope_type),
            scope_id=payload.scope_id,
            reason=payload.reason,
        )
    except access_req_svc.AccessRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    await audit_svc.write_audit(
        session,
        user_id=user.id,
        organization_id=user.organization_id,
        section="users",
        action="access_request_create",
        outcome=AuditOutcome.OK,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_payload=payload.model_dump(mode="json"),
    )
    await session.commit()

    # Notify admins after commit so a rollback doesn't surface a fake.
    await access_req_svc.notify_new_request(session, req)

    return await _to_public(session, req)


@router.get("", response_model=list[AccessRequestPublic])
async def list_access_requests(
    status_filter: AccessRequestStatus | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> list[AccessRequestPublic]:
    rows = await access_req_svc.list_requests(
        session,
        organization_id=user.organization_id,
        actor=user,
        status=status_filter,
    )
    return [await _to_public(session, r) for r in rows]


@router.get("/{request_id}", response_model=AccessRequestPublic)
async def get_access_request(
    request_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AccessRequestPublic:
    try:
        req = await access_req_svc.get_request(
            session,
            organization_id=user.organization_id,
            actor=user,
            request_id=request_id,
        )
    except access_req_svc.AccessRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except access_req_svc.AccessRequestForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    return await _to_public(session, req)


# ---------------- Decide ----------------


@router.post(
    "/{request_id}/approve",
    response_model=AccessRequestPublic,
)
async def approve_access_request(
    request_id: UUID,
    payload: AccessRequestApprove,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AccessRequestPublic:
    try:
        req = await access_req_svc.approve_request(
            session,
            request_id=request_id,
            actor=user,
            role_ids=payload.role_ids,
            expires_at=payload.expires_at,
            note=payload.note,
        )
    except access_req_svc.AccessRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except access_req_svc.AccessRequestForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except access_req_svc.AccessRequestAlreadyDecided as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except access_req_svc.AccessRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await session.commit()

    # Refetch with grants populated for response.
    fresh = (
        await session.execute(
            select(AccessRequest)
            .where(AccessRequest.id == req.id)
            .options(selectinload(AccessRequest.grants))
        )
    ).scalar_one()
    return await _to_public(session, fresh)


@router.post(
    "/{request_id}/deny",
    response_model=AccessRequestPublic,
)
async def deny_access_request(
    request_id: UUID,
    payload: AccessRequestDeny,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AccessRequestPublic:
    try:
        req = await access_req_svc.deny_request(
            session,
            request_id=request_id,
            actor=user,
            note=payload.note,
        )
    except access_req_svc.AccessRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except access_req_svc.AccessRequestForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except access_req_svc.AccessRequestAlreadyDecided as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    await session.commit()
    return await _to_public(session, req)


@router.post(
    "/{request_id}/cancel",
    response_model=AccessRequestPublic,
)
async def cancel_access_request(
    request_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> AccessRequestPublic:
    try:
        req = await access_req_svc.cancel_request(
            session, request_id=request_id, actor=user
        )
    except access_req_svc.AccessRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except access_req_svc.AccessRequestForbidden as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except access_req_svc.AccessRequestAlreadyDecided as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    await session.commit()
    return await _to_public(session, req)


# ---------------- Directory ----------------


@router.get("/-/directory", response_model=DirectoryReport)
async def list_directory(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> DirectoryReport:
    rows = await access_req_svc.directory(session, actor=user)
    return DirectoryReport(
        tenants=[
            DirectoryTenant(
                id=t["id"],
                name=t["name"],
                has_access=t["has_access"],
                sites=[
                    DirectorySite(
                        id=s["id"],
                        name=s["name"],
                        has_access=s["has_access"],
                        devices=[
                            DirectoryDevice(
                                id=d["id"],
                                name=d["name"],
                                has_access=d["has_access"],
                            )
                            for d in s["devices"]
                        ],
                    )
                    for s in t["sites"]
                ],
            )
            for t in rows
        ]
    )
