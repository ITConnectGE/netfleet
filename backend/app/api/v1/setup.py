"""First-run setup wizard endpoint."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import db_session
from app.core.config import settings
from app.schemas.auth import SetupRequest, SetupResponse
from app.services import setup as setup_svc

router = APIRouter()


class SetupStatus(BaseModel):
    setup_complete: bool


@router.get("/status", response_model=SetupStatus)
async def setup_status(session: AsyncSession = Depends(db_session)) -> SetupStatus:
    return SetupStatus(setup_complete=await setup_svc.setup_complete(session))


@router.post("", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
async def perform_setup(
    payload: SetupRequest,
    session: AsyncSession = Depends(db_session),
    x_bootstrap_token: str = Header(default=""),
) -> SetupResponse:
    # First-run takeover defence (reported by Bertie, 2026-05-31). When the
    # installer has provisioned a bootstrap token, the very first POST /setup
    # must carry it as `X-Bootstrap-Token`. Once `is_setup_complete=True` the
    # service returns 409 either way, so the token is single-use by virtue of
    # the DB state — there is no separate "consume" step to race.
    #
    # Empty BOOTSTRAP_TOKEN means "feature disabled" — keeps in-place upgrades
    # of already-configured orgs working (the endpoint will 409 on them
    # regardless), and lets dev installs skip the token. install.sh now writes
    # a real token on every new install so this branch is the exception.
    expected = settings.BOOTSTRAP_TOKEN
    if expected:
        # constant-time compare on bytes
        if not hmac.compare_digest(
            x_bootstrap_token.encode("utf-8"), expected.encode("utf-8")
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="invalid or missing bootstrap token",
            )

    try:
        org, user = await setup_svc.perform_setup(session, payload)
    except setup_svc.SetupAlreadyComplete as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    await session.commit()
    return SetupResponse(organization_id=org.id, user_id=user.id)
