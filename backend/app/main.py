from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.api.v1 import router as v1_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.logging import configure_logging

configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log.info("netfleet.startup", version=__version__, env=settings.ENV)
    await init_db()
    yield
    await close_db()
    log.info("netfleet.shutdown")


app = FastAPI(
    title="NetFleet API",
    description="Multi-vendor network fleet management for MSPs.",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Session middleware — required by Authlib's OIDC state/nonce storage.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.JWT_SECRET,
    same_site="lax",
    https_only=settings.ENV == "production",
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": "NetFleet API", "version": __version__, "docs": "/docs"}
