from collections.abc import AsyncIterator

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


async def init_db() -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(
        settings.DATABASE_URL,
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
