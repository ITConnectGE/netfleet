"""Per-user notification feed used by the navbar bell.

Currently derives two event kinds from existing tables:

  - ``firmware_update`` — devices where firmware_available diverges from
    firmware. Timestamp is firmware_checked_at (best proxy for "we
    learned this is available").
  - ``device_added`` — devices created recently.

A separate "notification log" table felt premature: the data we want to
surface is already in `devices`, and storing duplicates would force us
to keep them in sync. The watermark `users.notifications_seen_at`
splits items into read / unread without a join table.

If the feed later grows to include events that don't live in `devices`
(e.g. access requests in Stage 6), we'll introduce a proper
notifications table at that point.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import db_session, get_current_user
from app.models.device import Device
from app.models.user import User
from app.services.firmware import _norm_version  # type: ignore[attr-defined]

router = APIRouter()

# How many days back we expose a "device added" notification for after
# creation. After this window the event drops out of the feed even if
# the user never opened it — they have the Audit log for archeology.
DEVICE_ADDED_WINDOW_DAYS = 14

# How many feed rows we send the UI at most. The dropdown is meant
# to be a glanceable summary, not a paginated inbox.
MAX_FEED_ITEMS = 20


class NotificationItem(BaseModel):
    id: str
    kind: Literal["firmware_update", "device_added"]
    title: str
    subtitle: str | None
    timestamp: datetime
    link_path: str
    unread: bool


class NotificationFeed(BaseModel):
    unread_count: int
    items: list[NotificationItem]


@router.get("", response_model=NotificationFeed)
async def list_my_notifications(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> NotificationFeed:
    watermark = user.notifications_seen_at
    # Pulling all org devices is fine — fleet sizes are in the hundreds
    # at most for the MSPs we serve; if that ever changes we can slice
    # in SQL with WHERE created_at > NOW() - INTERVAL '14 days' OR
    # (firmware != firmware_available).
    rows = (
        await session.execute(
            select(Device).where(Device.organization_id == user.organization_id)
        )
    ).scalars().all()

    now = datetime.now(UTC)
    cutoff = now.timestamp() - DEVICE_ADDED_WINDOW_DAYS * 86400

    items: list[NotificationItem] = []
    for d in rows:
        # Firmware-available event.
        if d.firmware_available and d.firmware:
            cur = _norm_version(d.firmware)
            nxt = _norm_version(d.firmware_available)
            if cur and nxt and cur != nxt:
                ts = d.firmware_checked_at or d.updated_at or d.created_at
                items.append(
                    NotificationItem(
                        id=f"fw:{d.id}",
                        kind="firmware_update",
                        title=f"{d.name}: firmware {nxt} available",
                        subtitle=f"running {cur}",
                        timestamp=ts,
                        link_path=f"/dashboard/devices/{d.id}",
                        unread=_is_unread(ts, watermark),
                    )
                )

        # Newly-added device event (rolling 14-day window).
        if d.created_at.timestamp() >= cutoff:
            items.append(
                NotificationItem(
                    id=f"dev:{d.id}",
                    kind="device_added",
                    title=f"New device: {d.name}",
                    subtitle=d.host,
                    timestamp=d.created_at,
                    link_path=f"/dashboard/devices/{d.id}",
                    unread=_is_unread(d.created_at, watermark),
                )
            )

    items.sort(key=lambda i: i.timestamp, reverse=True)
    items = items[:MAX_FEED_ITEMS]
    unread_count = sum(1 for i in items if i.unread)
    return NotificationFeed(unread_count=unread_count, items=items)


@router.post("/mark-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notifications_read(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(db_session),
) -> None:
    user.notifications_seen_at = datetime.now(UTC)
    await session.commit()


def _is_unread(ts: datetime | None, watermark: datetime | None) -> bool:
    if ts is None:
        return False
    if watermark is None:
        return True
    return ts > watermark
