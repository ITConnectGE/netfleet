"""Collect + query the NetFleet API host's own resource stats.

Live snapshot is built per request from psutil — no DB hit. Historical
samples are persisted by the scheduler on a fixed cadence and capped
by row count rather than age so the table stays bounded regardless of
how long the host has been running. Cumulative byte counters are
stored verbatim; the UI turns the diff between adjacent rows into a
throughput rate. Per-IP outbound connection listing comes straight
from psutil's net_connections() — it shows live state (count of
connections per peer + total bytes for each open TCP socket the
kernel exposes), not a long-running byte history, which the operator
can correlate with the historical totals.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

import psutil
import structlog
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.host_metric import HostMetricSample

log = structlog.get_logger(__name__)


_ROW_BYTES = 96  # rough Postgres row width incl. tuple header + index entry
DEFAULT_MAX_BYTES = 5 * 1024 * 1024


def estimate_max_rows(max_bytes: int = DEFAULT_MAX_BYTES) -> int:
    """Translate the operator-friendly "≈5 MB cap" into a row count
    the prune query can act on."""
    return max(1000, max_bytes // _ROW_BYTES)


def _summed_net_io() -> tuple[int, int]:
    """Sum rx/tx across every non-loopback interface. Loopback skews
    container deployments because every internal DB call shows up
    there — operators care about traffic that crosses the box."""
    pernic = psutil.net_io_counters(pernic=True)
    rx = 0
    tx = 0
    for nic, c in pernic.items():
        if nic.startswith("lo"):
            continue
        rx += int(c.bytes_recv)
        tx += int(c.bytes_sent)
    return rx, tx


def collect_snapshot() -> dict[str, Any]:
    """Live point-in-time numbers — no DB hit."""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_pct = psutil.cpu_percent(interval=None)
    rx, tx = _summed_net_io()
    boot_ts = psutil.boot_time()
    return {
        "cpu_percent": float(cpu_pct),
        "cpu_count": int(psutil.cpu_count() or 0),
        "memory_used_bytes": int(mem.used),
        "memory_total_bytes": int(mem.total),
        "memory_percent": float(mem.percent),
        "disk_used_bytes": int(disk.used),
        "disk_total_bytes": int(disk.total),
        "disk_percent": float(disk.percent),
        "net_rx_bytes": rx,
        "net_tx_bytes": tx,
        "boot_at_unix": float(boot_ts),
    }


def collect_per_nic() -> list[dict[str, Any]]:
    """Per-interface cumulative byte counters + link status. Loopback
    is included so the operator can see container-internal chatter,
    but the aggregate summary skips it (see _summed_net_io)."""
    pernic = psutil.net_io_counters(pernic=True)
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    out: list[dict[str, Any]] = []
    for name, c in pernic.items():
        ipv4 = next(
            (a.address for a in addrs.get(name, []) if a.family.name == "AF_INET"),
            None,
        )
        s = stats.get(name)
        out.append(
            {
                "name": name,
                "ipv4": ipv4,
                "is_up": bool(s.isup) if s else False,
                "speed_mbps": int(s.speed) if s else 0,
                "rx_bytes": int(c.bytes_recv),
                "tx_bytes": int(c.bytes_sent),
                "rx_packets": int(c.packets_recv),
                "tx_packets": int(c.packets_sent),
                "errors_in": int(c.errin),
                "errors_out": int(c.errout),
            }
        )
    return sorted(out, key=lambda r: (-1 if r["name"].startswith("eth") else 0, r["name"]))


def collect_peer_connections() -> list[dict[str, Any]]:
    """Group every open TCP connection by remote IP. Returns one row
    per remote address with a connection count and the breakdown by
    state — enough to answer "what is the box talking to right now"
    without trying to invent per-IP byte history (kernel doesn't
    expose that without iptables-side counters, which we don't have
    in the unprivileged container)."""
    try:
        conns = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, PermissionError):
        # Non-root containers without CAP_SYS_PTRACE can't see other
        # processes' sockets; we still surface our own.
        try:
            conns = psutil.Process().net_connections(kind="tcp")
        except Exception as e:
            log.warning("host_metrics.peers.deny", error=str(e))
            return []
    by_ip: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"remote": "", "count": 0, "by_state": defaultdict(int)}
    )
    for c in conns:
        if c.raddr is None or not c.raddr.ip:
            continue
        ip = str(c.raddr.ip)
        rec = by_ip[ip]
        rec["remote"] = ip
        rec["count"] += 1
        rec["by_state"][c.status] = rec["by_state"][c.status] + 1
    # Flatten for JSON
    out: list[dict[str, Any]] = []
    for rec in by_ip.values():
        out.append(
            {
                "remote": rec["remote"],
                "count": int(rec["count"]),
                "by_state": dict(rec["by_state"]),
            }
        )
    return sorted(out, key=lambda r: -r["count"])


async def persist_snapshot(session: AsyncSession) -> HostMetricSample:
    """Insert a new sample row. Returns the row so the caller can
    attach metadata if needed."""
    snap = collect_snapshot()
    row = HostMetricSample(
        cpu_percent=snap["cpu_percent"],
        cpu_count=snap["cpu_count"],
        memory_used_bytes=snap["memory_used_bytes"],
        memory_total_bytes=snap["memory_total_bytes"],
        disk_used_bytes=snap["disk_used_bytes"],
        disk_total_bytes=snap["disk_total_bytes"],
        net_rx_bytes=snap["net_rx_bytes"],
        net_tx_bytes=snap["net_tx_bytes"],
    )
    session.add(row)
    await session.flush()
    return row


async def prune_history(
    session: AsyncSession, *, max_bytes: int = DEFAULT_MAX_BYTES
) -> int:
    """Trim oldest rows so total count stays at-or-under the cap.
    Returns the number of rows deleted in this pass."""
    cap = estimate_max_rows(max_bytes)
    count = int(
        (
            await session.execute(select(func.count()).select_from(HostMetricSample))
        ).scalar_one()
    )
    if count <= cap:
        return 0
    keep_ids_stmt = (
        select(HostMetricSample.id)
        .order_by(desc(HostMetricSample.sampled_at))
        .limit(cap)
    )
    del_stmt = delete(HostMetricSample).where(
        HostMetricSample.id.not_in(keep_ids_stmt)
    )
    return int((await session.execute(del_stmt)).rowcount or 0)


async def fetch_history(
    session: AsyncSession, *, limit: int = 240
) -> list[dict[str, Any]]:
    """Most recent N samples, oldest-first so the UI can plot
    left-to-right without reversing."""
    rows = list(
        (
            await session.execute(
                select(HostMetricSample)
                .order_by(desc(HostMetricSample.sampled_at))
                .limit(limit)
            )
        ).scalars()
    )
    rows.reverse()
    return [
        {
            "id": str(r.id),
            "sampled_at": r.sampled_at,
            "cpu_percent": r.cpu_percent,
            "cpu_count": r.cpu_count,
            "memory_used_bytes": r.memory_used_bytes,
            "memory_total_bytes": r.memory_total_bytes,
            "disk_used_bytes": r.disk_used_bytes,
            "disk_total_bytes": r.disk_total_bytes,
            "net_rx_bytes": r.net_rx_bytes,
            "net_tx_bytes": r.net_tx_bytes,
        }
        for r in rows
    ]


async def history_size_estimate(session: AsyncSession) -> dict[str, int]:
    """How much of the cap we're currently using — surfaced to the UI
    so the operator can see "history at 32% of cap". Cheap query."""
    count = int(
        (
            await session.execute(select(func.count()).select_from(HostMetricSample))
        ).scalar_one()
    )
    return {
        "rows": count,
        "approx_bytes": count * _ROW_BYTES,
        "cap_bytes": DEFAULT_MAX_BYTES,
    }
