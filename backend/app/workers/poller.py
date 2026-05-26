"""
Device status poller.

Run as a separate container (`worker` service in docker-compose). Periodically
iterates over enabled devices, calls each driver's `system_info()`, writes the
result to Redis (for fast UI fetch) and a long-term history table (Phase 6).

For Phase 1 this is a stub that logs a heartbeat.
"""

from __future__ import annotations

import asyncio
import signal

import structlog

from app.core.config import settings
from app.core.logging import configure_logging


async def main() -> None:
    configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    log = structlog.get_logger("netfleet.poller")

    log.info(
        "poller.start",
        interval=settings.POLLER_INTERVAL_SECONDS,
        concurrency=settings.POLLER_CONCURRENCY,
    )

    stopping = asyncio.Event()

    def _stop(signum: int, _: object) -> None:
        log.info("poller.signal", signum=signum)
        stopping.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop, sig, None)
        except NotImplementedError:
            # Windows fallback (dev only)
            signal.signal(sig, _stop)

    while not stopping.is_set():
        log.info("poller.tick", todo="iterate enabled devices in Phase 6")
        try:
            await asyncio.wait_for(stopping.wait(), timeout=settings.POLLER_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass

    log.info("poller.shutdown")


if __name__ == "__main__":
    asyncio.run(main())
