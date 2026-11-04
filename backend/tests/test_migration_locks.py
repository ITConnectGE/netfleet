"""The migration lock watcher ends only what keeps blocking the migration.

On 2026-11-03 `alembic upgrade head` waited 2h18m behind a backend whose
client (the replaced worker) was already gone; api never became healthy
and the updater left the UI down.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core import migration_locks


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    """`blockers` is a list consumed one entry per poll (last one repeats)."""

    def __init__(self, blockers, *, fail_first: bool = False):
        self.blockers = list(blockers)
        self.terminated: list[int] = []
        self.fail_first = fail_first

    def connect(self):
        db = self

        class _Conn:
            async def __aenter__(self):
                if db.fail_first:
                    db.fail_first = False
                    raise OSError("connection refused")
                return self

            async def __aexit__(self, *_a):
                return False

            async def execute(self, stmt, params=None):
                sql = str(stmt)
                if "pg_blocking_pids" in sql:
                    now = db.blockers[0] if len(db.blockers) == 1 else db.blockers.pop(0)
                    return _Result(now)
                if "pg_stat_activity" in sql:
                    return _Result(
                        [SimpleNamespace(state="active", age="02:17:00", q="DELETE FROM x")]
                    )
                if "pg_terminate_backend" in sql:
                    db.terminated.append(params["pid"])
                    return _Result([True])
                raise AssertionError(sql)

            async def commit(self):
                return None

        return _Conn()


async def _watch(db, seconds: float) -> None:
    task = asyncio.create_task(
        migration_locks.end_stale_blockers(db, 1, grace=0.05, poll=0.01)
    )
    await asyncio.sleep(seconds)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_persistent_blocker_is_terminated():
    db = _FakeDb([[4242]])
    await _watch(db, 0.2)
    assert 4242 in db.terminated


async def test_brief_blocker_is_left_alone():
    # Blocks for one poll, then lets go -- an ordinary short transaction.
    db = _FakeDb([[7], []])
    await _watch(db, 0.2)
    assert db.terminated == []


async def test_nothing_blocking_terminates_nothing():
    db = _FakeDb([[]])
    await _watch(db, 0.1)
    assert db.terminated == []


async def test_watcher_survives_a_failed_poll():
    db = _FakeDb([[99]], fail_first=True)
    await _watch(db, 0.25)
    assert 99 in db.terminated
