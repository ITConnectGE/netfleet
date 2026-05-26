"""Driver catalog — what vendors NetFleet can talk to right now."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.drivers import list_vendors
from app.models.user import User

router = APIRouter()


class DriverInfo(BaseModel):
    vendor: str
    display_name: str
    capabilities: list[str]


@router.get("", response_model=list[DriverInfo])
async def list_drivers(_: User = Depends(get_current_user)) -> list[DriverInfo]:
    return [DriverInfo(**d) for d in list_vendors()]
