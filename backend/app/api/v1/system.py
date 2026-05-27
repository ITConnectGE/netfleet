import os
import time

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__

router = APIRouter()

_started_at = time.monotonic()


def _running_version() -> str:
    """Prefer the deployed image tag (VERSION env, set by docker-compose) over
    the source `__version__` constant — those two can drift when version bumps
    in source land before the next tagged release."""
    return os.getenv("VERSION") or __version__


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
        current=_running_version(),
        channel="stable",
        repo="ITConnectGE/netfleet",
    )


async def health() -> HealthResponse:
    """Liveness probe — does NOT depend on DB/Redis being reachable."""
    return HealthResponse(
        status="ok",
        version=_running_version(),
        uptime_seconds=time.monotonic() - _started_at,
    )
