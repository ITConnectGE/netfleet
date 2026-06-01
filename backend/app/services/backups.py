"""Device backup service — runs the driver, stores artefacts on disk, records history."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.drivers import get_driver
from app.models.device import Device
from app.models.device_backup import BackupSource, BackupStatus, DeviceBackup
from app.services.device import _to_driver_creds, get_device

log = structlog.get_logger(__name__)

# Configurable via env later; for now a sensible default that matches install.sh paths.
BACKUP_ROOT = Path(os.environ.get("NETFLEET_BACKUP_ROOT", "/backups/devices"))


class BackupError(Exception):
    pass


def _device_dir(device_id: UUID) -> Path:
    d = BACKUP_ROOT / str(device_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def run_backup(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device_id: UUID,
    triggered_by_user_id: UUID | None,
    source: BackupSource,
) -> DeviceBackup:
    """Run a backup for one device and write the result row + files."""
    device = await get_device(session, organization_id, device_id)
    started = time.monotonic()
    ts = datetime.now(UTC)
    stamp = ts.strftime("%Y%m%d-%H%M%S")
    base_name = f"{stamp}"

    row = DeviceBackup(
        organization_id=organization_id,
        device_id=device_id,
        triggered_by_user_id=triggered_by_user_id,
        source=source,
        status=BackupStatus.FAILED,
    )

    try:
        artefact = await get_driver(device.vendor).system_backup(
            _to_driver_creds(device), ssh_port=device.ssh_port or 22
        )
        dir_ = _device_dir(device_id)
        backup_path = dir_ / f"{base_name}.backup"
        rsc_path = dir_ / f"{base_name}.rsc"

        backup_path.write_bytes(artefact.backup_bytes)
        rsc_path.write_text(artefact.rsc_text or "", encoding="utf-8")

        row.status = BackupStatus.OK
        row.backup_filename = backup_path.name
        row.rsc_filename = rsc_path.name
        row.backup_size_bytes = backup_path.stat().st_size
        row.rsc_size_bytes = rsc_path.stat().st_size
    except Exception as e:
        log.warning("backup.failed", device_id=str(device_id), error=str(e))
        row.error_message = str(e)[:1024]
    finally:
        row.duration_ms = int((time.monotonic() - started) * 1000)
        session.add(row)
        await session.flush()

    return row


async def list_history(
    session: AsyncSession,
    organization_id: UUID,
    *,
    device_id: UUID | None = None,
    limit: int = 100,
) -> list[DeviceBackup]:
    stmt = select(DeviceBackup).where(DeviceBackup.organization_id == organization_id)
    if device_id is not None:
        stmt = stmt.where(DeviceBackup.device_id == device_id)
    stmt = stmt.order_by(DeviceBackup.ts.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


def backup_file_path(device_id: UUID, filename: str) -> Path:
    """Resolve a backup filename safely under the device's directory (no traversal)."""
    base = _device_dir(device_id).resolve()
    p = (base / filename).resolve()
    if not str(p).startswith(str(base)):
        raise BackupError("path traversal blocked")
    if not p.is_file():
        raise BackupError("file not found")
    return p


async def backup_all_devices(
    session: AsyncSession, organization_id: UUID
) -> list[DeviceBackup]:
    """Iterate enabled devices in the org and back each one up sequentially."""
    stmt = select(Device).where(
        Device.organization_id == organization_id, Device.is_enabled.is_(True)
    )
    devices = list((await session.execute(stmt)).scalars())

    rows: list[DeviceBackup] = []
    for d in devices:
        try:
            row = await run_backup(
                session,
                organization_id=organization_id,
                device_id=d.id,
                triggered_by_user_id=None,
                source=BackupSource.SCHEDULED,
            )
            rows.append(row)
        except Exception as e:
            log.warning("backup.iteration_failed", device_id=str(d.id), error=str(e))
    return rows


async def apply_retention(
    session: AsyncSession, organization_id: UUID, keep_days: int = 30
) -> int:
    """Delete backup files + rows older than keep_days. Returns files removed."""
    cutoff = datetime.now(UTC) - timedelta(days=keep_days)
    stmt = select(DeviceBackup).where(
        DeviceBackup.organization_id == organization_id, DeviceBackup.ts < cutoff
    )
    rows = list((await session.execute(stmt)).scalars())
    removed = 0
    for row in rows:
        try:
            if row.backup_filename:
                p = _device_dir(row.device_id) / row.backup_filename
                if p.exists():
                    p.unlink()
                    removed += 1
            if row.rsc_filename:
                p = _device_dir(row.device_id) / row.rsc_filename
                if p.exists():
                    p.unlink()
                    removed += 1
        except Exception as e:
            log.warning("backup.retention_unlink_failed", path=str(p), error=str(e))
        await session.delete(row)
    await session.flush()
    return removed
