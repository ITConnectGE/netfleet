"""HTTP client to the updater container. Lives on the same internal network."""

from __future__ import annotations

import os

import httpx
import structlog

log = structlog.get_logger(__name__)

UPDATER_URL = os.getenv("NETFLEET_UPDATER_URL", "http://updater:8080")


class UpdaterUnreachable(Exception):
    pass


class UpdateInProgress(Exception):
    pass


def _token() -> str:
    return os.getenv("NETFLEET_UPDATER_TOKEN", "changeme")


async def get_status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{UPDATER_URL}/status")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise UpdaterUnreachable(str(e)) from e


async def trigger_update(target_version: str, *, backup: bool = True) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{UPDATER_URL}/update",
                headers={"X-Internal-Token": _token()},
                json={"version": target_version, "backup": backup},
            )
            if r.status_code == 409:
                raise UpdateInProgress(r.json().get("detail", "update in progress"))
            r.raise_for_status()
            return r.json()
    except UpdateInProgress:
        raise
    except Exception as e:
        raise UpdaterUnreachable(str(e)) from e
