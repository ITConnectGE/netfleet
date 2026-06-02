import os
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.dependencies import db_session, get_current_user
from app.models.user import User
from app.services import host_metrics as host_metrics_svc

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


# ---------------- NetFleet host stats ----------------


class HostHealthResponse(BaseModel):
    """Live snapshot of CPU / memory / disk / network from psutil."""

    sampled_at: datetime
    cpu_percent: float
    cpu_count: int
    memory_used_bytes: int
    memory_total_bytes: int
    memory_percent: float
    disk_used_bytes: int
    disk_total_bytes: int
    disk_percent: float
    net_rx_bytes: int
    net_tx_bytes: int
    boot_at_unix: float
    nics: list[dict[str, Any]]
    peers: list[dict[str, Any]]


class HostHistoryPoint(BaseModel):
    sampled_at: datetime
    cpu_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    disk_used_bytes: int
    disk_total_bytes: int
    net_rx_bytes: int
    net_tx_bytes: int


class HostHistoryResponse(BaseModel):
    points: list[HostHistoryPoint]
    capacity: dict[str, int]


@router.get("/host-health", response_model=HostHealthResponse)
async def host_health(
    _: User = Depends(get_current_user),
) -> HostHealthResponse:
    snap = host_metrics_svc.collect_snapshot()
    return HostHealthResponse(
        sampled_at=datetime.now().astimezone(),
        cpu_percent=snap["cpu_percent"],
        cpu_count=snap["cpu_count"],
        memory_used_bytes=snap["memory_used_bytes"],
        memory_total_bytes=snap["memory_total_bytes"],
        memory_percent=snap["memory_percent"],
        disk_used_bytes=snap["disk_used_bytes"],
        disk_total_bytes=snap["disk_total_bytes"],
        disk_percent=snap["disk_percent"],
        net_rx_bytes=snap["net_rx_bytes"],
        net_tx_bytes=snap["net_tx_bytes"],
        boot_at_unix=snap["boot_at_unix"],
        nics=host_metrics_svc.collect_per_nic(),
        peers=host_metrics_svc.collect_peer_connections(),
    )


@router.get("/host-history", response_model=HostHistoryResponse)
async def host_history(
    points: int = Query(default=240, ge=1, le=2000),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> HostHistoryResponse:
    rows = await host_metrics_svc.fetch_history(session, limit=points)
    cap = await host_metrics_svc.history_size_estimate(session)
    return HostHistoryResponse(
        points=[
            HostHistoryPoint(
                sampled_at=r["sampled_at"],
                cpu_percent=r["cpu_percent"],
                memory_used_bytes=r["memory_used_bytes"],
                memory_total_bytes=r["memory_total_bytes"],
                disk_used_bytes=r["disk_used_bytes"],
                disk_total_bytes=r["disk_total_bytes"],
                net_rx_bytes=r["net_rx_bytes"],
                net_tx_bytes=r["net_tx_bytes"],
            )
            for r in rows
        ],
        capacity=cap,
    )
