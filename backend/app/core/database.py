import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _json_default(obj: object) -> object:
    # Python's stdlib json.dumps doesn't know about UUID/datetime/Decimal; without
    # this, any JSONB column receiving a UUID (e.g. audit_logs.request_payload)
    # raises TypeError at flush time.
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _json_serializer(obj: object) -> str:
    return json.dumps(obj, default=_json_default)


async def init_db() -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(
        settings.DATABASE_URL,
        json_serializer=_json_serializer,
        echo=settings.ENV == "development" and settings.LOG_LEVEL == "DEBUG",
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def close_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Database not initialized — call init_db() first.")
    async with _sessionmaker() as session:
        yield session
