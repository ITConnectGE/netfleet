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
    # First-run takeover defence (reported by Bertie 2026-05-31, hardened
    # against an empty-token fail-open per his 2026-06-01 follow-up).
    #
    # Two states to handle:
    #
    #   (a) Setup already complete (`is_setup_complete=True`). The endpoint
    #       returns 409 — the token is consumed implicitly by the DB state
    #       transition, so a leaked token is not a re-use risk.
    #
    #   (b) Setup NOT complete. We MUST require a configured server token
    #       and a matching X-Bootstrap-Token header. An empty server token
    #       used to be treated as "feature disabled" so legacy upgrades kept
    #       working — but that left dev / hand-rolled `docker compose up`
    #       deployments fail-open (anyone wins the admin account). Now we
    #       fail closed with 503 telling the operator how to set the token.
    expected = settings.BOOTSTRAP_TOKEN

    already_complete = await setup_svc.setup_complete(session)
    if not already_complete:
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "First-run setup is disabled: NETFLEET_BOOTSTRAP_TOKEN "
                    "is not configured. Generate one (`openssl rand -hex 32`), "
                    "set it in /opt/netfleet/.env, and restart the api service."
                ),
            )
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
