"""HTTP middleware — request-id binding and a global exception trap.

Every request gets a UUID (or honours an upstream X-Request-Id from Caddy
if present). The id is:
  * bound onto structlog's context so every log line for that request
    carries it automatically
  * echoed back as the X-Request-Id response header
  * surfaced in any 500 response body, so a user reporting "I got a 500"
    can quote the id and we can grep the api logs for it
"""

from __future__ import annotations

import secrets
import traceback

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger("netfleet.http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Bind a stable request-id onto every request + the structlog context."""

    HEADER = "x-request-id"

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(self.HEADER) or secrets.token_hex(8)
        request.state.request_id = rid

        # Each request gets a fresh bound context — clear() prevents one
        # request's values leaking into the next (asyncio task chains share
        # the contextvar by default).
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=rid,
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response.headers[self.HEADER] = rid
        return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """500 trap. Logs full traceback; returns a JSON body with the request-id
    so the user can quote it back to support."""
    rid = getattr(request.state, "request_id", None)
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log.error(
        "request.unhandled_exception",
        request_id=rid,
        method=request.method,
        path=request.url.path,
        exc_type=exc.__class__.__name__,
        exc_message=str(exc),
        traceback=tb,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": rid,
            "exc_type": exc.__class__.__name__,
            # Short message only — never the traceback, which can leak internals.
            "exc_message": str(exc)[:500],
        },
        headers={RequestIdMiddleware.HEADER: rid} if rid else {},
    )
