"""SMS gateway service — generic HTTP webhook with per-provider presets.

Designed to slot in any SMS REST gateway by parameterising URL, method,
body format, and auth header. Presets pre-fill the wire-format fields
for known providers so the user only has to paste their API key and
sender. The runtime sender side is `send_sms(org, to, content)`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field, encrypt_field
from app.models.organization import Organization
from app.schemas.settings import SmsSettingsUpdate

log = structlog.get_logger(__name__)


class SmsGatewayError(Exception):
    pass


# ---------------- Provider presets ----------------
#
# Stored in code so a new gateway can be added with a single dict entry
# (no migration). The user can always override every field in the UI.

PRESETS: dict[str, dict[str, Any]] = {
    "smsoffice": {
        "key": "smsoffice",
        "label": "SMS Office (smsoffice.ge)",
        # GET with query-string params, per
        # https://smsoffice.ge/integration/
        "api_url": "https://smsoffice.ge/api/v2/send/",
        "http_method": "GET",
        "body_format": "query",
        "body_template": "key={key}&destination={destination}&sender={sender}&content={content}",
        "auth_header_name": None,
        "auth_header_value_template": None,
        "success_status_min": 200,
        "success_status_max": 299,
        # smsoffice returns a JSON response that includes "Success" on
        # delivery; treat anything but a 2xx as failed.
        "success_body_contains": None,
        "notes": (
            "Get the API key from the smsoffice.ge dashboard. Sender must be "
            "an approved alphanumeric sender ID on your account."
        ),
    },
    "custom": {
        "key": "custom",
        "label": "Custom HTTP gateway",
        "api_url": "",
        "http_method": "POST",
        "body_format": "form",
        "body_template": "key={key}&to={destination}&from={sender}&text={content}",
        "auth_header_name": None,
        "auth_header_value_template": None,
        "success_status_min": 200,
        "success_status_max": 299,
        "success_body_contains": None,
        "notes": (
            "Templates use {key}, {sender}, {destination}, {content} placeholders. "
            "body_format=query sends them in the URL, form sends "
            "application/x-www-form-urlencoded, json sends a JSON object."
        ),
    },
}


def list_presets() -> list[dict[str, Any]]:
    return list(PRESETS.values())


# ---------------- CRUD ----------------


async def get_org(session: AsyncSession, organization_id: UUID) -> Organization:
    org = (
        await session.execute(select(Organization).where(Organization.id == organization_id))
    ).scalar_one_or_none()
    if org is None:
        raise SmsGatewayError("organization not found")
    return org


async def update_sms(
    session: AsyncSession,
    organization_id: UUID,
    payload: SmsSettingsUpdate,
) -> Organization:
    org = await get_org(session, organization_id)
    data = payload.model_dump(exclude_unset=True)

    if "sms_api_key" in data:
        raw = data.pop("sms_api_key")
        org.sms_api_key_encrypted = encrypt_field(raw) if raw else None

    for key, value in data.items():
        setattr(org, key, value)

    await session.flush()
    return org


# ---------------- Render + send ----------------


def _placeholders(org: Organization, *, destination: str, content: str) -> dict[str, str]:
    key = decrypt_field(org.sms_api_key_encrypted) if org.sms_api_key_encrypted else ""
    return {
        "key": key,
        "sender": org.sms_sender or "",
        "destination": destination,
        "content": content,
    }


def _render(template: str | None, values: dict[str, str], *, url_encode: bool) -> str:
    if not template:
        return ""
    # Two-pass: replace exact placeholders, leaving any unknown {x} alone.
    # Manual sub instead of str.format so a literal "{" in the body
    # template doesn't blow up when the user has copy-pasted JSON.
    out = template
    for k, v in values.items():
        replacement = quote_plus(v) if url_encode else v
        out = out.replace("{" + k + "}", replacement)
    return out


async def send_sms(
    session: AsyncSession,
    organization_id: UUID,
    *,
    destination: str,
    content: str,
) -> tuple[int, str]:
    """Dispatch a single SMS via the configured gateway. Returns (http_status,
    response_body). Raises SmsGatewayError if disabled or unconfigured. The
    caller decides whether to swallow the error (e.g. for fire-and-forget
    notifications) or surface it."""
    org = await get_org(session, organization_id)
    if not org.sms_enabled:
        raise SmsGatewayError("SMS gateway is disabled in settings")
    if not org.sms_api_url or not org.sms_body_template:
        raise SmsGatewayError("SMS gateway is not fully configured (url + body template)")

    values = _placeholders(org, destination=destination, content=content)

    method = (org.sms_http_method or "POST").upper()
    body_format = (org.sms_body_format or "form").lower()
    url = org.sms_api_url

    headers: dict[str, str] = {}
    if org.sms_auth_header_name and org.sms_auth_header_value_template:
        headers[org.sms_auth_header_name] = _render(
            org.sms_auth_header_value_template, values, url_encode=False
        )

    request_kwargs: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
        "timeout": org.sms_timeout_seconds or 10,
    }

    if body_format == "query":
        rendered = _render(org.sms_body_template, values, url_encode=True)
        sep = "&" if "?" in url else "?"
        request_kwargs["url"] = f"{url}{sep}{rendered}"
    elif body_format == "form":
        rendered = _render(org.sms_body_template, values, url_encode=False)
        request_kwargs["content"] = rendered.encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")
    elif body_format == "json":
        rendered = _render(org.sms_body_template, values, url_encode=False)
        request_kwargs["content"] = rendered.encode("utf-8")
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
    else:
        raise SmsGatewayError(f"unknown sms_body_format: {body_format!r}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.request(**request_kwargs)
    except httpx.HTTPError as e:
        raise SmsGatewayError(f"HTTP request failed: {e}") from e

    body = resp.text[:1024]
    in_range = org.sms_success_status_min <= resp.status_code <= org.sms_success_status_max
    if not in_range:
        raise SmsGatewayError(
            f"gateway returned {resp.status_code} (expected {org.sms_success_status_min}–{org.sms_success_status_max}): {body}"
        )
    if org.sms_success_body_contains and org.sms_success_body_contains not in body:
        raise SmsGatewayError(
            f"gateway response missing expected text {org.sms_success_body_contains!r}: {body}"
        )
    return resp.status_code, body


async def test_sms(
    session: AsyncSession,
    organization_id: UUID,
    *,
    destination: str,
    content: str,
) -> tuple[bool, int | None, str | None, str | None]:
    """Same as send_sms but never raises — returns (ok, status, body, error).
    Also persists the result onto the org for the UI's 'last test' badge."""
    org = await get_org(session, organization_id)
    ok = False
    status_code: int | None = None
    body: str | None = None
    err: str | None = None
    try:
        status_code, body = await send_sms(
            session,
            organization_id,
            destination=destination,
            content=content,
        )
        ok = True
    except SmsGatewayError as e:
        err = str(e)
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"

    org.sms_last_test_at = datetime.now(UTC)
    org.sms_last_test_ok = ok
    org.sms_last_test_message = err if not ok else f"HTTP {status_code}: {(body or '')[:200]}"
    await session.flush()
    return ok, status_code, body, err
