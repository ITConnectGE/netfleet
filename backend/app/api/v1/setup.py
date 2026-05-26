"""First-run setup wizard endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import db_session
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
) -> SetupResponse:
    try:
        org, user = await setup_svc.perform_setup(session, payload)
    except setup_svc.SetupAlreadyComplete as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    await session.commit()
    return SetupResponse(organization_id=org.id, user_id=user.id)
