"""
NetFleet updater — drives in-app self-update via the host's Docker socket.

Endpoints:
  GET  /status   — current vs latest version + state machine + recent log
  POST /update   — triggers the background update flow (requires INTERNAL_TOKEN)
  GET  /health   — liveness probe

The updater container runs separately from the rest of the stack and is
intentionally excluded from `docker compose up` during the update so it does
not commit suicide mid-recreate. `api`, `worker`, and `web` are recreated;
`postgres`, `redis`, and `caddy` keep running. `api`'s entrypoint runs
`alembic upgrade head` on startup, so migrations happen automatically.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from collections import deque
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import httpx
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

log = structlog.get_logger("netfleet.updater")

CURRENT_VERSION = os.getenv("VERSION", "0.1.0")

# Mounted by docker-compose; see the `updater:` service in docker-compose.yml.
WORKDIR = Path(os.getenv("NETFLEET_WORKDIR", "/workdir"))
BACKUPS_DIR = Path(os.getenv("NETFLEET_BACKUPS_DIR", "/backups"))
COMPOSE_FILE = WORKDIR / "docker-compose.yml"
ENV_FILE = WORKDIR / ".env"

# Services we recreate on update (NEVER include 'updater' here — see module docstring)
RECREATE_SERVICES = ["api", "worker", "web"]

API_HEALTH_URL = os.getenv(
    "NETFLEET_API_HEALTH_URL", "http://api:8000/api/v1/health"
)
HEALTH_TIMEOUT_SECONDS = 180


def _normalize_image_tag(version: str) -> str:
    """GitHub tags look like `v0.13.1` but our GHCR images publish without the
    leading `v` (the release workflow's `type=semver,pattern={{version}}` strips
    it). Compose interpolates whatever we set as VERSION into the image tag, so
    we have to match the GHCR convention or the pull resolves to "not found"."""
    return version.lstrip("v").strip()


def _env_value(key: str, default: str) -> str:
    """Read a single value from the workdir .env file (best-effort; falls back to default)."""
    if not ENV_FILE.exists():
        return default
    try:
        for ln in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if ln.startswith(f"{key}="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return default


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
    HEALTH_CHECKING = "health_checking"
    SUCCESS = "success"
    FAILED = "failed"


# ---------------- State ----------------


class _State:
    """In-memory state. Reset on updater restart (acceptable — fresh state is safer)."""

    def __init__(self) -> None:
        self.state: UpdateState = UpdateState.IDLE
        self.target_version: str | None = None
        self.available: str | None = None
        self.last_checked_iso: str | None = None
        self.last_error: str | None = None
        self.started_at_iso: str | None = None
        self.finished_at_iso: str | None = None
        self.log_lines: deque[str] = deque(maxlen=200)

    def append_log(self, line: str) -> None:
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        self.log_lines.append(f"{stamp} {line}")
        log.info("updater.log", line=line)

    def set_state(self, new_state: UpdateState, *, log_line: str | None = None) -> None:
        self.state = new_state
        if log_line:
            self.append_log(log_line)


_state = _State()


class StatusResponse(BaseModel):
    current: str
    available: str | None = None
    target_version: str | None = None
    channel: str
    repo: str
    state: UpdateState
    last_checked_iso: str | None = None
    last_error: str | None = None
    started_at_iso: str | None = None
    finished_at_iso: str | None = None
    log_tail: list[str]


class UpdateRequest(BaseModel):
    version: str
    backup: bool = True


# ---------------- GitHub poll ----------------


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
        _state.last_error = f"github poll: {e}"
        return None


# ---------------- Shell helpers ----------------


async def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    """Run a subprocess, stream its output into the state log. Raises on non-zero exit."""
    pretty = " ".join(shlex.quote(p) for p in cmd)
    _state.append_log(f"$ {pretty}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace").rstrip()
        if line:
            _state.append_log(line)
    rc = await proc.wait()
    if rc != 0:
        raise RuntimeError(f"`{pretty}` exited with status {rc}")


async def _docker_compose(args: list[str], *, env: dict[str, str] | None = None) -> None:
    await _run(["docker", "compose", "-f", str(COMPOSE_FILE), *args], env=env)


# ---------------- Pre-update DB backup ----------------


async def _backup_postgres(target_version: str) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_path = BACKUPS_DIR / f"pre-update-{target_version}-{stamp}.sql.gz"
    _state.append_log(f"backup -> {out_path.name}")

    # Read DB user/db from the host's .env (the updater container does NOT inherit
    # the API's NETFLEET_DB_* env vars). Defaults match install.sh.
    db_user = _env_value("NETFLEET_DB_USER", "netfleet")
    db_name = _env_value("NETFLEET_DB_NAME", "netfleet")

    # Pipe `pg_dump | gzip` through bash since asyncio doesn't pipe processes natively.
    pipeline = (
        f"docker compose -f {shlex.quote(str(COMPOSE_FILE))} "
        f"exec -T postgres pg_dump -U {shlex.quote(db_user)} {shlex.quote(db_name)} "
        f"| gzip > {shlex.quote(str(out_path))}"
    )
    await _run(["bash", "-lc", pipeline])
    return out_path


# ---------------- Persist new VERSION to .env ----------------


async def _persist_version(version: str) -> None:
    """Update or append VERSION= in /workdir/.env so future compose calls use it."""
    if not ENV_FILE.exists():
        _state.append_log(f".env not found at {ENV_FILE}; skipping VERSION persist")
        return
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    replaced = False
    for ln in lines:
        if ln.startswith("VERSION="):
            out.append(f"VERSION={version}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(f"VERSION={version}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    _state.append_log(f"persisted VERSION={version} to .env")


# ---------------- Health check ----------------


async def _wait_for_health(timeout: int) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    last_err: str | None = None
    async with httpx.AsyncClient(timeout=5) as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(API_HEALTH_URL)
                if r.status_code == 200:
                    _state.append_log(f"api healthy: {r.json()}")
                    return
                last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = str(e)
            await asyncio.sleep(3)
    raise RuntimeError(f"api never came back healthy (last error: {last_err})")


# ---------------- The flow ----------------


async def _run_update(target_version: str, backup: bool) -> None:
    # The release publishes images as `0.13.1`, but the GitHub tag is `v0.13.1`.
    # Strip the prefix once and use the image tag everywhere from here on.
    image_tag = _normalize_image_tag(target_version)
    _state.target_version = target_version
    _state.started_at_iso = datetime.now(UTC).isoformat()
    _state.finished_at_iso = None
    _state.last_error = None
    _state.log_lines.clear()
    _state.append_log(f"=== Starting update to {target_version} (image tag {image_tag}) ===")

    try:
        if backup and settings.AUTO_BACKUP_ON_UPDATE:
            _state.set_state(UpdateState.BACKING_UP, log_line="Backing up postgres…")
            await _backup_postgres(image_tag)

        env = {**os.environ, "VERSION": image_tag}

        _state.set_state(UpdateState.PULLING, log_line=f"Pulling images @ {image_tag}…")
        await _docker_compose(["pull", *RECREATE_SERVICES], env=env)

        _state.set_state(UpdateState.RECREATING, log_line="Recreating api/worker/web…")
        # --no-deps so we don't touch postgres/redis (stateful) or updater (us).
        await _docker_compose(
            ["up", "-d", "--no-deps", *RECREATE_SERVICES], env=env
        )

        _state.set_state(
            UpdateState.HEALTH_CHECKING,
            log_line="Waiting for api to come back healthy…",
        )
        await _wait_for_health(HEALTH_TIMEOUT_SECONDS)

        await _persist_version(image_tag)

        _state.finished_at_iso = datetime.now(UTC).isoformat()
        _state.set_state(
            UpdateState.SUCCESS, log_line=f"=== Update to {target_version} complete ==="
        )
    except Exception as e:
        _state.last_error = str(e)
        _state.finished_at_iso = datetime.now(UTC).isoformat()
        _state.set_state(UpdateState.FAILED, log_line=f"FAILED: {e}")
        log.exception("update.failed", error=str(e))


# ---------------- Auth ----------------


def _require_token(x_internal_token: str = Header(default="")) -> None:
    if x_internal_token != settings.UPDATER_TOKEN:
        raise HTTPException(status_code=401, detail="invalid internal token")


# ---------------- App ----------------


app = FastAPI(title="NetFleet Updater", version=CURRENT_VERSION)


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    available = await _check_latest_release()
    _state.available = available
    _state.last_checked_iso = datetime.now(UTC).isoformat()
    show_available = (
        available if (available and available.lstrip("v") != CURRENT_VERSION.lstrip("v")) else None
    )
    return StatusResponse(
        current=CURRENT_VERSION,
        available=show_available,
        target_version=_state.target_version,
        channel=settings.UPDATE_CHANNEL,
        repo=settings.GITHUB_REPO,
        state=_state.state,
        last_checked_iso=_state.last_checked_iso,
        last_error=_state.last_error,
        started_at_iso=_state.started_at_iso,
        finished_at_iso=_state.finished_at_iso,
        log_tail=list(_state.log_lines),
    )


@app.post(
    "/update",
    status_code=202,
    dependencies=[Depends(_require_token)],
)
async def trigger_update(req: UpdateRequest) -> dict[str, str]:
    if _state.state in (
        UpdateState.BACKING_UP,
        UpdateState.PULLING,
        UpdateState.RECREATING,
        UpdateState.HEALTH_CHECKING,
    ):
        raise HTTPException(
            status_code=409, detail=f"update already in progress: {_state.state.value}"
        )
    # Fire-and-forget — the background task drives the state machine.
    asyncio.create_task(_run_update(req.version, req.backup))
    return {"status": "accepted", "target_version": req.version}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": CURRENT_VERSION}
