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
import secrets
import shlex
import time
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

# Mounted by docker-compose; see the `updater:` service in docker-compose.yml.
WORKDIR = Path(os.getenv("NETFLEET_WORKDIR", "/workdir"))
BACKUPS_DIR = Path(os.getenv("NETFLEET_BACKUPS_DIR", "/backups"))
COMPOSE_FILE = WORKDIR / "docker-compose.yml"
ENV_FILE = WORKDIR / ".env"


def _current_version() -> str:
    """Always reflect the *deployed* image tag — the source of truth is the
    VERSION line written into /workdir/.env by `_persist_version` after each
    successful upgrade. Falls back to the env var (set by the host shell) and
    finally to "unknown" so we never silently return a stale "0.1.0"."""
    return _env_value("VERSION", os.getenv("VERSION", "unknown"))

# Services we recreate on update (NEVER include 'updater' here — see module docstring)
RECREATE_SERVICES = ["api", "worker", "web"]

API_HEALTH_URL = os.getenv(
    "NETFLEET_API_HEALTH_URL", "http://api:8000/api/v1/health"
)
HEALTH_TIMEOUT_SECONDS = 180

# How long a release-check answer stays good. Long enough that routine
# UI polling costs ~6 GitHub calls an hour instead of 180; short enough
# that a release published while you are watching shows up on its own.
CHECK_CACHE_SECONDS = float(os.getenv("NETFLEET_CHECK_CACHE_SECONDS", "600"))

# Baked into the image at build time. The updater deliberately excludes
# itself from `docker compose up` during an update so it cannot kill
# itself mid-upgrade — which also means it never picks up its own fixes.
# Reporting the version lets the UI say so out loud.
__version__ = "0.52.0"


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
    # Optional. Unauthenticated requests to api.github.com share a single
    # 60/hr bucket per source IP, which a deployment behind office NAT
    # exhausts in a few polls (the worker also queries the same host
    # under user actions). A classic PAT with NO scopes (public repo) or
    # a fine-grained token with read-only "Contents" + "Metadata" scopes
    # raises the limit to 5,000/hr and is enough for this updater.
    GITHUB_TOKEN: str = ""


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
        # Kept apart from `last_error`, which belongs to update *runs*. A
        # failed release poll and a failed upgrade are different problems,
        # and sharing one field means whichever happened last hides the
        # other. This one is cleared on every successful poll.
        self.check_error: str | None = None
        # Last tag GitHub gave us, and when. Every /status call used to
        # issue a fresh GitHub request, and the UI polls status every 30 s
        # from the Updates page plus every 60 s from the banner on every
        # other page — 180 requests/hour against an unauthenticated limit
        # of 60, so the instance sat permanently rate-limited and reported
        # "up to date" forever.
        self.cached_tag: str | None = None
        self.cached_at: float = 0.0
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
    # The updater's own image version. It excludes itself from the recreate
    # so it cannot kill itself mid-update, which also means it never picks
    # up its own fixes — when this lags `current`, the operator needs to
    # recreate it by hand and should be told so.
    updater_version: str = __version__
    available: str | None = None
    target_version: str | None = None
    channel: str
    repo: str
    state: UpdateState
    last_checked_iso: str | None = None
    last_error: str | None = None
    # Set when the release poll itself failed. `available: null` alone is
    # ambiguous — it means both "you are on the newest release" and "we
    # could not find out", and the UI used to render both as "up to date".
    check_error: str | None = None
    started_at_iso: str | None = None
    finished_at_iso: str | None = None
    log_tail: list[str]


class UpdateRequest(BaseModel):
    version: str
    backup: bool = True


# ---------------- GitHub poll ----------------


def _describe(e: Exception) -> str:
    """Turn a poll failure into something an operator can act on.

    The rate-limit case is worth naming: unauthenticated GitHub API calls
    are capped at 60/hour per IP, which a busy instance can exhaust, and
    the generic 403 text gives no hint that a token fixes it.
    """
    if isinstance(e, httpx.HTTPStatusError):
        resp = e.response
        if resp.status_code in (403, 429) and resp.headers.get("x-ratelimit-remaining") == "0":
            reset = resp.headers.get("x-ratelimit-reset")
            when = ""
            if reset and reset.isdigit():
                when = datetime.fromtimestamp(int(reset), UTC).strftime(" (resets %H:%M UTC)")
            return (
                f"GitHub API rate limit reached{when} — set NETFLEET_GITHUB_TOKEN "
                "to raise the limit"
            )
        if resp.status_code == 401:
            return "GitHub rejected NETFLEET_GITHUB_TOKEN (401)"
        return f"GitHub returned HTTP {resp.status_code}"
    if isinstance(e, httpx.TimeoutException):
        return "timed out talking to GitHub"
    if isinstance(e, httpx.RequestError):
        return f"network error reaching GitHub ({type(e).__name__})"
    return str(e)


async def _check_latest_release(*, force: bool = False) -> str | None:
    """Ask GitHub for the latest release tag.

    When `force` is True we sidestep two layers of staleness that bit users:
      1. GitHub's own `/releases/latest` pointer can lag the actual newest
         non-draft tag by a few minutes after a release lands. With force=True
         we fetch the recent release LIST and pick the highest, draft- and
         prerelease-filtered.
      2. Edge caches (and httpx connection reuse) sometimes return a cached
         body. Add a `Cache-Control: no-cache` header and a random query
         string so we cut both.
    """
    # Serve a recent answer rather than asking again. A release does not
    # appear more than once every few minutes, and the cost of asking every
    # time is a rate-limit ban that makes the whole feature lie.
    if not force and _state.cached_tag and (
        time.monotonic() - _state.cached_at < CHECK_CACHE_SECONDS
    ):
        return _state.cached_tag

    headers = {"Accept": "application/vnd.github+json"}
    if settings.GITHUB_TOKEN:
        # GitHub accepts both "token <pat>" (classic) and "Bearer <pat>"
        # (fine-grained). Bearer is the documented form for both today.
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    if force:
        headers["Cache-Control"] = "no-cache"

    if not force:
        url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/releases/latest"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 404:
                    # Either the repo has no releases yet or GITHUB_REPO is
                    # wrong. Both are worth saying out loud — silently
                    # reporting "up to date" forever is how a misconfigured
                    # instance goes years without an upgrade.
                    _state.check_error = (
                        f"no published releases found for '{settings.GITHUB_REPO}' "
                        "(check NETFLEET_GITHUB_REPO)"
                    )
                    return None
                r.raise_for_status()
                _state.check_error = None
                tag = r.json().get("tag_name")
                if tag:
                    _state.cached_tag = tag
                    _state.cached_at = time.monotonic()
                return tag
        except Exception as e:
            _state.check_error = f"could not reach GitHub: {_describe(e)}"
            # Keep serving the last good answer: a blip must not make a
            # known-available update vanish from the screen.
            return _state.cached_tag

    # Forced path: list mode + cache buster.
    bust = secrets.token_hex(4)
    url = f"https://api.github.com/repos/{settings.GITHUB_REPO}/releases?per_page=30&_={bust}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 404:
                _state.check_error = (
                    f"no published releases found for '{settings.GITHUB_REPO}' "
                    "(check NETFLEET_GITHUB_REPO)"
                )
                return None
            r.raise_for_status()
            releases = r.json()
    except Exception as e:
        _state.check_error = f"could not reach GitHub: {_describe(e)}"
        return _state.cached_tag

    def _key(rel: dict) -> tuple[int, ...]:
        tag = (rel.get("tag_name") or "").lstrip("v")
        parts: list[int] = []
        for p in tag.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                # Anything non-numeric (rc1, beta, …) sorts below numeric.
                return (-1,)
        return tuple(parts)

    candidates = [
        rel
        for rel in releases
        if not rel.get("draft") and not rel.get("prerelease") and rel.get("tag_name")
    ]
    if not candidates:
        _state.check_error = (
            f"'{settings.GITHUB_REPO}' has no published release "
            "(only drafts or pre-releases)"
        )
        return None
    candidates.sort(key=_key, reverse=True)
    _state.check_error = None
    tag = candidates[0].get("tag_name")
    if tag:
        _state.cached_tag = tag
        _state.cached_at = time.monotonic()
    return tag


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


# ---------------- Image cleanup ----------------


async def _prune_old_images() -> None:
    """Remove unreferenced images older than the rollback window.

    `docker image prune -af --filter until=72h` removes images that
      (a) are not used by any container (running OR stopped), AND
      (b) were created more than 72 hours ago.

    Anything we just pulled stays — `created` is the image's build
    timestamp from the registry, but Docker's prune actually checks
    when the image was last referenced locally, which is the moment of
    the pull. So the current and previous-batch images survive while
    the long tail of stale tags gets reclaimed.
    """
    _state.append_log("$ docker image prune -af --filter until=72h")
    await _run(["docker", "image", "prune", "-af", "--filter", "until=72h"])


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

        # House-keeping — reclaim disk from the previous-version images so the
        # host doesn't slowly fill up after a string of upgrades. A 72h `until`
        # filter keeps anything pulled in the last three days (so the prior
        # version is still around for an emergency rollback) and never touches
        # images that are currently in use.
        try:
            await _prune_old_images()
        except Exception as e:  # noqa: BLE001
            _state.append_log(f"image prune skipped: {e}")

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


app = FastAPI(title="NetFleet Updater", version=_current_version())


@app.get("/status", response_model=StatusResponse)
async def status(force: bool = False) -> StatusResponse:
    available = await _check_latest_release(force=force)
    _state.available = available
    _state.last_checked_iso = datetime.now(UTC).isoformat()
    current = _current_version()
    show_available = (
        available if (available and available.lstrip("v") != current.lstrip("v")) else None
    )
    return StatusResponse(
        current=current,
        updater_version=__version__,
        available=show_available,
        target_version=_state.target_version,
        channel=settings.UPDATE_CHANNEL,
        repo=settings.GITHUB_REPO,
        state=_state.state,
        last_checked_iso=_state.last_checked_iso,
        last_error=_state.last_error,
        check_error=_state.check_error,
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
    return {"status": "ok", "version": _current_version()}
