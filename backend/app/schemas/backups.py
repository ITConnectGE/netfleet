from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.device_backup import BackupSource, BackupStatus


class DeviceBackupPublic(BaseModel):
    id: UUID
    ts: datetime
    device_id: UUID
    triggered_by_user_id: UUID | None
    source: BackupSource
    status: BackupStatus
    backup_filename: str | None
    rsc_filename: str | None
    backup_size_bytes: int | None
    rsc_size_bytes: int | None
    error_message: str | None
    duration_ms: int | None
