"""
NetFleet updater (Phase 1 stub).

Responsibilities:
- Periodically poll GitHub Releases for newer version
- Expose /status (current vs available, plus state machine for ongoing update)
- Expose /update (triggered by api with shared INTERNAL_TOKEN)
- Pre-update DB backup, docker compose pull + up -d, health check, rollback on failure

Phase 1 ships endpoints with stub behavior. Phase 7 fills in the docker socket
calls and rollback state machine.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from enum import StrEnum

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

CURRENT_VERSION = os.getenv("VERSION", "0.1.0")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NETFLEET_", case_sensitive=False, extra="ignore")

    UPDATER_TOKEN: str = "changeme"
    UPDATE_CHANNEL: str = "stable"
    GITHUB_REPO: str = "ITConnectGE/netfleet"
    AUTO_BACKUP_ON_UPDATE: bool = True


settings = Settings()


class UpdateState(StrEnum):
    IDLE = "idle"
    CHECKING = "checking"
    BACKING_UP = "backing_up"
    PULLING = "pulling"
    RECREATING = "recreating"
    MIGRATING = "migrating"
    HEALTH_CHECKING = "health_checking"
    SUCCESS = "success"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class StatusResponse(BaseModel):
    current: str
    available: str | None = None
    channel: str
    repo: str
    state: UpdateState
    last_checked_iso: str | None = None
    last_error: str | None = None


class UpdateRequest(BaseModel):
    version: str
    backup: bool = True


_state: dict[str, object] = {
    "state": UpdateState.IDLE,
    "available": None,
    "last_checked_iso": None,
    "last_error": None,
}


async def _check_latest_release() -> str | None:
    url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers={"Accept": "application/vnd.github+json"})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json().get("tag_name")
    except Exception as e:
        _state["last_error"] = str(e)
        return None


def _require_token(x_internal_token: str = Header(default="")) -> None:
    if x_internal_token != settings.UPDATER_TOKEN:
        raise HTTPException(status_code=401, detail="invalid internal token")


app = FastAPI(title="NetFleet Updater", version=CURRENT_VERSION)


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    available = await _check_latest_release()
    _state["available"] = available
    _state["last_checked_iso"] = datetime.now(UTC).isoformat()
    return StatusResponse(
        current=CURRENT_VERSION,
        available=available if available and available != CURRENT_VERSION else None,
        channel=settings.UPDATE_CHANNEL,
        repo=settings.GITHUB_REPO,
        state=UpdateState(_state["state"]),
        last_checked_iso=str(_state["last_checked_iso"]),
        last_error=_state.get("last_error"),  # type: ignore[arg-type]
    )


@app.post("/update", dependencies=[Depends(_require_token)])
async def trigger_update(req: UpdateRequest) -> dict[str, str]:
    """Phase 1 stub. Full implementation in Phase 7."""
    if _state["state"] not in (UpdateState.IDLE, UpdateState.SUCCESS, UpdateState.ROLLED_BACK, UpdateState.FAILED):
        raise HTTPException(status_code=409, detail=f"update in progress: {_state['state']}")

    _state["state"] = UpdateState.PULLING
    return {
        "status": "accepted",
        "version": req.version,
        "note": "Phase 1 stub — full update pipeline lands in Phase 7",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": CURRENT_VERSION}
