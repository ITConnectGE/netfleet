from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.api.v1 import router as v1_router
from app.core.config import settings
from app.core.database import close_db, init_db, session_factory
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware, unhandled_exception_handler
from app.drivers.base import UnsupportedOperation
from app.services.change_guard import expire_stale_guards
from app.services.device import HostKeyNotPinned
from app.services.packages import mark_orphaned_runs

configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log.info("netfleet.startup", version=__version__, env=settings.ENV)
    await init_db()

    # Package runs live in a background task, so an API restart orphans any
    # that were in flight. The command may well have finished on the host —
    # what ended was our ability to watch it — but a row that still claims
    # to be running months later is worse than one that admits as much.
    try:
        async with session_factory()() as session:
            closed = await mark_orphaned_runs(session)
        if closed:
            log.info("packages.orphaned_runs_closed", count=closed)
    except Exception as e:  # noqa: BLE001 - never block startup on housekeeping
        log.warning("packages.orphan_sweep_failed", error=str(e))

    # Same reasoning for firewall guards. The host restored itself when its
    # timer fired; what NetFleet lost was the chance to observe it, and a row
    # that still claims to be armed is a pending change that will never
    # resolve.
    try:
        async with session_factory()() as session:
            expired = await expire_stale_guards(session)
        if expired:
            log.info("change_guard.stale_guards_expired", count=expired)
    except Exception as e:  # noqa: BLE001 - never block startup on housekeeping
        log.warning("change_guard.expiry_sweep_failed", error=str(e))

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

# Request-id + structlog binding. Outermost so the id is bound for every
# subsequent middleware and handler.
app.add_middleware(RequestIdMiddleware)

# Catch-all for anything an endpoint forgets to handle — turns opaque 500s
# into a structured log line + a JSON body carrying the request_id.
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(v1_router, prefix="/api/v1")


@app.exception_handler(UnsupportedOperation)
async def _unsupported_operation(
    request: Request, exc: UnsupportedOperation
) -> JSONResponse:
    # A driver only implements what its platform has. Asking for the rest is
    # a 501, not a crash — the UI hides those sections, but a stale tab or a
    # direct API call can still arrive.
    return JSONResponse(status_code=501, content={"detail": str(exc)})


@app.exception_handler(HostKeyNotPinned)
async def _host_key_not_pinned(request: Request, exc: HostKeyNotPinned) -> JSONResponse:
    # Raised from `_to_driver_creds`, which every driver-mediated endpoint
    # funnels through. Handled centrally so each of the ~60 call sites does
    # not have to catch it, and so it reads as an actionable 409 rather than
    # an opaque 500.
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
async def _log_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Default FastAPI behavior plus a structured log line so 422s in prod are
    # diagnosable from logs alone. We log only `loc` + `msg` (never the raw
    # body or `input`) so passwords/tokens never reach the log sink.
    log.warning(
        "validation.failed",
        method=request.method,
        path=request.url.path,
        errors=[{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()],
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": "NetFleet API", "version": __version__, "docs": "/docs"}
