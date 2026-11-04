"""Per-request context that the audit writer reads implicitly.

`current_session_id` is the sign-in session the request belongs to: the
`sid` claim of its access token, or the session a login / refresh just
started. Every audit row written while handling the request carries it,
so the audit log can be grouped by session without threading the id
through 100+ `write_audit` call sites. Background jobs never set it.
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

current_session_id: ContextVar[UUID | None] = ContextVar("current_session_id", default=None)
