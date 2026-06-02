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


def _zero_snapshot() -> dict[str, Any]:
    return {
        "cpu_percent": 0.0,
        "cpu_count": 0,
        "memory_used_bytes": 0,
        "memory_total_bytes": 0,
        "memory_percent": 0.0,
        "disk_used_bytes": 0,
        "disk_total_bytes": 0,
        "disk_percent": 0.0,
        "net_rx_bytes": 0,
        "net_tx_bytes": 0,
        "boot_at_unix": 0.0,
    }


def collect_snapshot() -> dict[str, Any]:
    """Live point-in-time numbers — no DB hit. Each psutil call is
    wrapped so a single failure (typically `disk_usage('/')` on a
    container with a stripped root mount, or `net_connections` denied
    by AppArmor) degrades gracefully to zero rather than 500-ing the
    whole endpoint."""
    out = _zero_snapshot()
    try:
        out["cpu_percent"] = float(psutil.cpu_percent(interval=None))
    except Exception as e:  # noqa: BLE001
        log.warning("host_metrics.cpu_percent.failed", error=str(e))
    try:
        out["cpu_count"] = int(psutil.cpu_count() or 0)
    except Exception as e:  # noqa: BLE001
        log.warning("host_metrics.cpu_count.failed", error=str(e))
    try:
        mem = psutil.virtual_memory()
        out["memory_used_bytes"] = int(mem.used)
        out["memory_total_bytes"] = int(mem.total)
        out["memory_percent"] = float(mem.percent)
    except Exception as e:  # noqa: BLE001
        log.warning("host_metrics.memory.failed", error=str(e))
    try:
        disk = psutil.disk_usage("/")
        out["disk_used_bytes"] = int(disk.used)
        out["disk_total_bytes"] = int(disk.total)
        out["disk_percent"] = float(disk.percent)
    except Exception as e:  # noqa: BLE001
        log.warning("host_metrics.disk.failed", error=str(e))
    try:
        rx, tx = _summed_net_io()
        out["net_rx_bytes"] = rx
        out["net_tx_bytes"] = tx
    except Exception as e:  # noqa: BLE001
        log.warning("host_metrics.net_io.failed", error=str(e))
    try:
        out["boot_at_unix"] = float(psutil.boot_time())
    except Exception as e:  # noqa: BLE001
        log.warning("host_metrics.boot_time.failed", error=str(e))
    return out


def collect_per_nic() -> list[dict[str, Any]]:
    """Per-interface cumulative byte counters + link status. Loopback
    is included so the operator can see container-internal chatter,
    but the aggregate summary skips it (see _summed_net_io)."""
    try:
        pernic = psutil.net_io_counters(pernic=True)
    except Exception as e:  # noqa: BLE001
        log.warning("host_metrics.pernic.failed", error=str(e))
        return []
    try:
        addrs = psutil.net_if_addrs()
    except Exception:  # noqa: BLE001
        addrs = {}
    try:
        stats = psutil.net_if_stats()
    except Exception:  # noqa: BLE001
        stats = {}
    out: list[dict[str, Any]] = []
    for name, c in pernic.items():
        try:
            ipv4 = next(
                (
                    a.address
                    for a in addrs.get(name, [])
                    if getattr(a.family, "name", "") == "AF_INET"
                ),
                None,
            )
        except Exception:  # noqa: BLE001
            ipv4 = None
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
    in the unprivileged container).

    Failure modes are all degraded to "empty list" because the host-
    health endpoint shouldn't 500 just because the API container is
    forbidden from reading /proc/<other-pid>/net."""
    conns: list = []
    try:
        conns = list(psutil.net_connections(kind="tcp"))
    except (psutil.AccessDenied, PermissionError):
        try:
            # `net_connections` was renamed from `connections` in psutil
            # 6; keep a getattr fallback so 5.x still works if it ever
            # gets pinned that way.
            proc = psutil.Process()
            fn = getattr(proc, "net_connections", None) or getattr(
                proc, "connections", None
            )
            if fn:
                conns = list(fn(kind="tcp"))
        except Exception as e:  # noqa: BLE001
            log.warning("host_metrics.peers.deny", error=str(e))
            return []
    except Exception as e:  # noqa: BLE001
        log.warning("host_metrics.peers.failed", error=str(e))
        return []

    by_ip: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"remote": "", "count": 0, "by_state": defaultdict(int)}
    )
    for c in conns:
        try:
            # raddr is `()` (empty tuple) for listening sockets, not
            # None — so `c.raddr is None` is False and the later
            # `.ip` access raises AttributeError. Truthy check handles
            # both cases.
            raddr = getattr(c, "raddr", None)
            if not raddr:
                continue
            ip = getattr(raddr, "ip", None)
            if not ip:
                continue
            ip_str = str(ip)
            rec = by_ip[ip_str]
            rec["remote"] = ip_str
            rec["count"] += 1
            state = getattr(c, "status", "UNKNOWN") or "UNKNOWN"
            rec["by_state"][state] = rec["by_state"][state] + 1
        except Exception:  # noqa: BLE001
            continue

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
