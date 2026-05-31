"""System-level backup: full pg_dump + device backup files + meta.json.

Bundles everything an MSP needs to migrate NetFleet to another host:
  - Postgres dump (compressed)
  - The on-disk device backup tree (/backups/devices/*)
  - meta.json with version, schema head, created_at, org name
  - restore.sh that drives a manual restore against `docker compose`

What is intentionally NOT in the bundle:
  - NETFLEET_JWT_SECRET / NETFLEET_FERNET_KEY (in .env)
    Without those keys the encrypted device credentials in the DB are
    useless, so the operator MUST copy .env across separately. The
    bundle's restore.sh checks for it and refuses to run without it.
    This is deliberate: combining secrets and data in one downloadable
    artefact is a security foot-gun.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import settings
from app.models.organization import Organization

log = structlog.get_logger(__name__)

BACKUP_ROOT = Path(os.environ.get("NETFLEET_BACKUP_ROOT", "/backups"))
SYSTEM_DIR = BACKUP_ROOT / "system"
DEVICES_DIR = BACKUP_ROOT / "devices"


# ---------------- Database connection parsing ----------------


def _pg_env_from_url(url: str) -> dict[str, str]:
    """Pull the connection bits out of NETFLEET_DATABASE_URL so we can pass
    them to pg_dump via standard libpq env vars (no shell quoting headaches)."""
    # Accept both `postgresql://` and `postgresql+asyncpg://`.
    if "+" in url.split("://", 1)[0]:
        url = url.replace("+asyncpg", "").replace("+psycopg", "").replace("+psycopg2", "")
    p = urlparse(url)
    env = os.environ.copy()
    if p.hostname:
        env["PGHOST"] = p.hostname
    if p.port:
        env["PGPORT"] = str(p.port)
    if p.username:
        env["PGUSER"] = p.username
    if p.password:
        env["PGPASSWORD"] = p.password
    if p.path and p.path.lstrip("/"):
        env["PGDATABASE"] = p.path.lstrip("/")
    return env


# ---------------- Bundle helpers ----------------


def _restore_script(version: str, db_name: str) -> str:
    return f"""#!/usr/bin/env bash
# NetFleet system restore — generated for v{version}.
#
# Usage (on the destination host, AFTER you have copied /opt/netfleet/.env
# across — the bundle does NOT contain JWT / Fernet keys on purpose):
#
#   bash restore.sh /path/to/this-bundle.tar.gz
#
# This will stop api/web/worker, drop and recreate the {db_name} database,
# load db.sql.gz into it, copy backups/devices/* into /opt/netfleet/data/
# backups/devices/, then restart the stack.

set -euo pipefail

BUNDLE="${{1:-}}"
if [ -z "$BUNDLE" ] || [ ! -f "$BUNDLE" ]; then
  echo "usage: $0 <path-to-netfleet-bundle.tar.gz>" >&2
  exit 1
fi

NETFLEET_DIR="${{NETFLEET_DIR:-/opt/netfleet}}"
if [ ! -f "$NETFLEET_DIR/.env" ]; then
  echo "$NETFLEET_DIR/.env not found — copy it across from the source host first." >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
tar -xzf "$BUNDLE" -C "$WORK"

# Read connection info from the destination's .env so we restore into the
# right place even if the new host renamed the user/db.
set -a
. "$NETFLEET_DIR/.env"
set +a
DB_USER="${{NETFLEET_DB_USER:-netfleet}}"
DB_NAME="${{NETFLEET_DB_NAME:-netfleet}}"

cd "$NETFLEET_DIR"

echo "==> Stopping api / web / worker"
docker compose stop api web worker

echo "==> Dropping and recreating database $DB_NAME"
docker compose exec -T postgres psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"
docker compose exec -T postgres psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

echo "==> Loading dump"
gunzip -c "$WORK/db.sql.gz" | docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME"

if [ -d "$WORK/backups" ]; then
  echo "==> Copying device backup files"
  mkdir -p "$NETFLEET_DIR/data/backups"
  cp -a "$WORK/backups/." "$NETFLEET_DIR/data/backups/"
fi

echo "==> Starting api / web / worker"
docker compose start api web worker

echo "Done. Open https://your-domain and click 'Test connection' on each device."
"""


async def create_system_backup(
    session: AsyncSession, *, organization_id: UUID
) -> Path:
    """Build the bundle synchronously inside an asyncio.to_thread so the API
    request stays unblocked. Returns the path to the on-disk artefact."""
    org = (
        await session.execute(select(Organization).where(Organization.id == organization_id))
    ).scalar_one()
    org_slug = org.slug
    db_url = settings.DATABASE_URL
    env = _pg_env_from_url(db_url)
    db_name = env.get("PGDATABASE", "netfleet")

    SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC)
    stamp = ts.strftime("%Y%m%d-%H%M%S")
    name = f"netfleet-system-{org_slug}-v{__version__}-{stamp}.tar.gz"
    out_path = SYSTEM_DIR / name

    def _build() -> None:
        with tempfile.TemporaryDirectory(prefix="netfleet-sysbackup-") as tmp:
            tmp_dir = Path(tmp)

            # 1. pg_dump piped through gzip so we don't keep an uncompressed
            #    dump on disk.
            sql_gz = tmp_dir / "db.sql.gz"
            with gzip.open(sql_gz, "wb") as gz:
                proc = subprocess.Popen(
                    [
                        "pg_dump",
                        "--no-owner",
                        "--clean",
                        "--if-exists",
                        "--quote-all-identifiers",
                    ],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                assert proc.stdout is not None
                while True:
                    chunk = proc.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    gz.write(chunk)
                rc = proc.wait()
                if rc != 0:
                    err = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", "replace")
                    raise RuntimeError(f"pg_dump failed (rc={rc}): {err.strip()}")

            # 2. meta.json
            meta = {
                "netfleet_version": __version__,
                "created_at": ts.isoformat(),
                "organization_slug": org_slug,
                "organization_name": org.name,
                "database_name": db_name,
                "bundle_format_version": 1,
            }
            meta_path = tmp_dir / "meta.json"
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

            # 3. restore.sh
            restore_path = tmp_dir / "restore.sh"
            restore_path.write_text(_restore_script(__version__, db_name), encoding="utf-8")

            # 4. Tar it up: meta + db + restore + devices/ subtree.
            with tarfile.open(out_path, "w:gz", compresslevel=6) as tf:
                tf.add(meta_path, arcname="meta.json")
                tf.add(sql_gz, arcname="db.sql.gz")
                tf.add(restore_path, arcname="restore.sh")
                if DEVICES_DIR.is_dir():
                    tf.add(DEVICES_DIR, arcname="backups/devices")

    await asyncio.to_thread(_build)
    log.info(
        "system_backup.created",
        path=str(out_path),
        size=out_path.stat().st_size,
        org=org_slug,
        version=__version__,
    )
    return out_path


def list_system_backups() -> list[dict[str, object]]:
    # Be tolerant of a misconfigured /backups mount — the alternative is
    # a 500 on every settings page load. Returning an empty list lets
    # the UI show "no bundles yet" until the operator fixes the mount or
    # the directory permissions.
    try:
        SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        log.warning("system_backup.system_dir_unavailable", error=str(e), path=str(SYSTEM_DIR))
        return []
    rows: list[dict[str, object]] = []
    try:
        for p in sorted(SYSTEM_DIR.iterdir(), reverse=True):
            if not p.is_file() or not p.name.endswith(".tar.gz"):
                continue
            st = p.stat()
            rows.append(
                {
                    "filename": p.name,
                    "size_bytes": st.st_size,
                    "created_at": datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
                }
            )
    except (PermissionError, OSError) as e:
        log.warning("system_backup.iter_failed", error=str(e), path=str(SYSTEM_DIR))
    return rows


def resolve_backup_path(filename: str) -> Path:
    SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    base = SYSTEM_DIR.resolve()
    p = (base / filename).resolve()
    if not str(p).startswith(str(base)):
        raise FileNotFoundError("path traversal blocked")
    if not p.is_file():
        raise FileNotFoundError(filename)
    return p


def delete_system_backup(filename: str) -> None:
    p = resolve_backup_path(filename)
    p.unlink()
    log.info("system_backup.deleted", filename=filename)


def used_disk_bytes() -> int:
    try:
        if not SYSTEM_DIR.exists():
            return 0
        return sum(p.stat().st_size for p in SYSTEM_DIR.iterdir() if p.is_file())
    except (PermissionError, OSError):
        return 0


def free_disk_bytes() -> int:
    try:
        target = SYSTEM_DIR if SYSTEM_DIR.exists() else SYSTEM_DIR.parent
        return shutil.disk_usage(target).free
    except (FileNotFoundError, PermissionError, OSError):
        return 0
