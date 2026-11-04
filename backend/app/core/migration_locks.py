"""Keep `alembic upgrade head` from waiting hours on an orphaned lock.

A migration that needs a table lock waits behind every open transaction on
that table. When an update replaces the old worker mid-query, Postgres does
not notice the client is gone until TCP gives up -- over two hours -- and the
orphaned backend keeps its locks the whole time. On 2026-11-03 the 0028
migration sat behind exactly that (a worker's event-retention DELETE), api
never came up, and the updater left the UI down. Anything that still blocks
the migration after a grace period is a leftover from the containers being
replaced, so it is terminated, and logged.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

BLOCKER_GRACE_SECONDS = 30
_POLL_SECONDS = 5


async def end_stale_blockers(
    engine,
    migration_pid: int,
    *,
    grace: float = BLOCKER_GRACE_SECONDS,
    poll: float = _POLL_SECONDS,
) -> None:
    first_seen: dict[int, float] = {}
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(poll)
        try:
            async with engine.connect() as conn:
                pids = (
                    await conn.execute(
                        text("SELECT unnest(pg_blocking_pids(:pid))"), {"pid": migration_pid}
                    )
                ).scalars().all()
                now = loop.time()
                first_seen = {p: first_seen.get(p, now) for p in pids}
                for pid, since in first_seen.items():
                    if now - since < grace:
                        continue
                    row = (
                        await conn.execute(
                            text(
                                "SELECT state, now() - xact_start AS age, left(query, 120) AS q "
                                "FROM pg_stat_activity WHERE pid = :pid"
                            ),
                            {"pid": pid},
                        )
                    ).first()
                    print(
                        f"[netfleet-api] migration blocked by pid {pid} "
                        f"({row.state if row else '?'}, xact age {row.age if row else '?'}): "
                        f"{row.q if row else ''!r} -- terminating it",
                        flush=True,
                    )
                    await conn.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
                await conn.commit()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # the watcher must never fail the migration
            print(f"[netfleet-api] migration lock watcher: {e}", flush=True)
