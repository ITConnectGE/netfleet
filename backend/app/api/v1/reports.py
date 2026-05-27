"""Reports — aggregated views of audit_log + secret_reveals + secret_rotations.

Each endpoint accepts ?format=csv to stream a CSV download. JSON view is
capped at ROW_CAP rows for browser responsiveness; CSV downloads the same
cap (raise it via SQL if you need everything).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import db_session, require_permission
from app.models.user import User
from app.schemas.reports import (
    ChangeReport,
    DeviceActivityReport,
    SecretAccessReport,
    UserActivityReport,
)
from app.services import device as device_svc
from app.services import reports as reports_svc

router = APIRouter()


# ---------------- Helpers ----------------


def _csv_stream(rows: list[dict], columns: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(columns)
    for r in rows:
        writer.writerow([_csv_cell(r.get(c)) for c in columns])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        import json

        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def _default_range(
    ts_from: datetime | None, ts_to: datetime | None
) -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    if ts_to is None:
        ts_to = now
    if ts_from is None:
        ts_from = ts_to - timedelta(days=30)
    return ts_from, ts_to


# ---------------- User activity ----------------


@router.get("/user-activity", response_model=UserActivityReport)
async def user_activity_report(
    user_id: UUID | None = Query(default=None),
    ts_from: datetime | None = Query(default=None),
    ts_to: datetime | None = Query(default=None),
    format: Literal["json", "csv"] = Query(default="json"),
    actor: User = Depends(require_permission("audit", "read")),
    session: AsyncSession = Depends(db_session),
):
    ts_from, ts_to = _default_range(ts_from, ts_to)
    rows, summary, truncated = await reports_svc.user_activity(
        session,
        organization_id=actor.organization_id,
        user_id=user_id,
        ts_from=ts_from,
        ts_to=ts_to,
    )

    if format == "csv":
        return _csv_stream(
            rows,
            [
                "ts",
                "user_email",
                "section",
                "action",
                "outcome",
                "device_name",
                "site_name",
                "tenant_name",
                "ip_address",
            ],
            f"user-activity-{ts_from.date()}_to_{ts_to.date()}.csv",
        )

    return UserActivityReport(
        range_from=ts_from,
        range_to=ts_to,
        rows=rows,
        summary=summary,
        truncated=truncated,
    )


# ---------------- Device activity ----------------


@router.get("/device-activity", response_model=DeviceActivityReport)
async def device_activity_report(
    device_id: UUID = Query(...),
    ts_from: datetime | None = Query(default=None),
    ts_to: datetime | None = Query(default=None),
    format: Literal["json", "csv"] = Query(default="json"),
    actor: User = Depends(require_permission("audit", "read")),
    session: AsyncSession = Depends(db_session),
):
    ts_from, ts_to = _default_range(ts_from, ts_to)

    # Make sure the device belongs to this org (avoids info leak via the
    # plain device-activity report)
    try:
        await device_svc.get_device(session, actor.organization_id, device_id)
    except device_svc.DeviceNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    device_name, rows, truncated = await reports_svc.device_activity(
        session,
        organization_id=actor.organization_id,
        device_id=device_id,
        ts_from=ts_from,
        ts_to=ts_to,
    )

    if format == "csv":
        return _csv_stream(
            rows,
            [
                "ts",
                "user_email",
                "section",
                "action",
                "outcome",
                "ip_address",
                "error_message",
                "request_payload",
            ],
            f"device-{device_name or device_id}-{ts_from.date()}_to_{ts_to.date()}.csv",
        )

    return DeviceActivityReport(
        device_id=device_id,
        device_name=device_name,
        range_from=ts_from,
        range_to=ts_to,
        rows=rows,
        truncated=truncated,
    )


# ---------------- Secret access ----------------


@router.get("/secret-access", response_model=SecretAccessReport)
async def secret_access_report(
    user_id: UUID | None = Query(default=None),
    ts_from: datetime | None = Query(default=None),
    ts_to: datetime | None = Query(default=None),
    format: Literal["json", "csv"] = Query(default="json"),
    actor: User = Depends(require_permission("audit", "read")),
    session: AsyncSession = Depends(db_session),
):
    ts_from, ts_to = _default_range(ts_from, ts_to)
    rows, unrotated = await reports_svc.secret_access(
        session,
        organization_id=actor.organization_id,
        user_id=user_id,
        ts_from=ts_from,
        ts_to=ts_to,
    )

    if format == "csv":
        return _csv_stream(
            rows,
            [
                "ts",
                "user_email",
                "device_name",
                "secret_kind",
                "secret_identifier",
                "secret_label",
                "last_rotation_ts",
                "rotated_since_reveal",
                "ip_address",
                "justification",
            ],
            f"secret-access-{ts_from.date()}_to_{ts_to.date()}.csv",
        )

    return SecretAccessReport(
        range_from=ts_from,
        range_to=ts_to,
        rows=rows,
        unrotated_count=unrotated,
    )


# ---------------- Changes ----------------


@router.get("/changes", response_model=ChangeReport)
async def change_report(
    section: str | None = Query(default=None, max_length=64),
    ts_from: datetime | None = Query(default=None),
    ts_to: datetime | None = Query(default=None),
    format: Literal["json", "csv"] = Query(default="json"),
    actor: User = Depends(require_permission("audit", "read")),
    session: AsyncSession = Depends(db_session),
):
    ts_from, ts_to = _default_range(ts_from, ts_to)
    rows, by_section, by_user, truncated = await reports_svc.changes(
        session,
        organization_id=actor.organization_id,
        ts_from=ts_from,
        ts_to=ts_to,
        section=section,
    )

    if format == "csv":
        return _csv_stream(
            rows,
            [
                "ts",
                "user_email",
                "section",
                "action",
                "outcome",
                "device_name",
                "request_payload",
            ],
            f"changes-{ts_from.date()}_to_{ts_to.date()}.csv",
        )

    return ChangeReport(
        range_from=ts_from,
        range_to=ts_to,
        rows=rows,
        by_section=by_section,
        by_user=by_user,
        truncated=truncated,
    )
