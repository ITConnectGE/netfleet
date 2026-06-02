"""Periodic snapshot of the NetFleet API host's own resource usage.

One row every NETFLEET_HOST_METRIC_INTERVAL seconds (default 60). The
scheduler prunes rows when the table grows past
NETFLEET_HOST_METRIC_MAX_ROWS (default ~52 000 — ≈ 5 MB at the row
size we land on after Postgres overhead). Keeping a hard cap rather
than a date window makes "we hold roughly N MB of history" the
property the operator can reason about, regardless of how often we
adjust the sample interval.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Float, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HostMetricSample(Base):
    """A single point-in-time snapshot of NetFleet's own host stats."""

    __tablename__ = "host_metric_samples"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    # CPU — percent across all cores, 0..100. -1 when unavailable.
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    cpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Memory — bytes. used vs total tells the operator both
    # "what fraction is left" and "how big is this box".
    memory_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memory_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Disk — root volume only. Same shape as memory.
    disk_used_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_total_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Network — cumulative byte counters since the host booted; the UI
    # turns the diff between rows into a throughput rate.
    net_rx_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    net_tx_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
