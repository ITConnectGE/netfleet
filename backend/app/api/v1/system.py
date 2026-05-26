import time

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter()

_started_at = time.monotonic()


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float


class VersionResponse(BaseModel):
    current: str
    channel: str
    repo: str


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    """Current running NetFleet version and update channel."""
    return VersionResponse(
        current=__version__,
        channel="stable",
        repo="ITConnectGE/netfleet",
    )


async def health() -> HealthResponse:
    """Liveness probe — does NOT depend on DB/Redis being reachable."""
    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_seconds=time.monotonic() - _started_at,
    )
