"""SMTP send helper that reads its config from the organization row.

Falls back to env-based settings (NETFLEET_SMTP_*) only when the org has
no smtp_host configured — preserves the v0.2.x behavior for deployments
that already worked off .env.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import structlog

from app.core.config import settings as app_settings
from app.core.security import decrypt_field
from app.models.organization import Organization

log = structlog.get_logger(__name__)


class SmtpNotConfigured(Exception):
    pass


class SmtpSendError(Exception):
    pass


def _resolve_config(org: Organization) -> dict[str, object]:
    """Return the SMTP config to use (org first, env fallback). Raises if neither is usable."""
    host = org.smtp_host or app_settings.SMTP_HOST
    if not host:
        raise SmtpNotConfigured("SMTP host is not configured")

    use_org = bool(org.smtp_host)
    password = ""
    if use_org and org.smtp_password_encrypted:
        try:
            password = decrypt_field(org.smtp_password_encrypted)
        except ValueError as e:
            raise SmtpSendError(f"cannot decrypt SMTP password: {e}") from e
    elif not use_org:
        password = app_settings.SMTP_PASSWORD

    return {
        "host": host,
        "port": org.smtp_port if use_org else app_settings.SMTP_PORT,
        "username": (org.smtp_username if use_org else app_settings.SMTP_USER) or "",
        "password": password,
        "use_tls": org.smtp_use_tls if use_org else app_settings.SMTP_TLS,
        "use_starttls": org.smtp_use_starttls if use_org else app_settings.SMTP_TLS,
        "from_email": (org.smtp_from_email if use_org else app_settings.SMTP_FROM) or "",
        "from_name": (org.smtp_from_name if use_org else "") or "",
    }


def _send_blocking(cfg: dict[str, object], msg: EmailMessage) -> None:
    host = str(cfg["host"])
    port = int(cfg["port"])
    use_tls = bool(cfg["use_tls"])
    use_starttls = bool(cfg["use_starttls"])
    username = str(cfg["username"])
    password = str(cfg["password"])

    ctx = ssl.create_default_context()

    if use_tls and not use_starttls:
        # Implicit TLS (typically port 465)
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            if username:
                s.login(username, password)
            s.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=30) as s:
        s.ehlo()
        if use_starttls:
            s.starttls(context=ctx)
            s.ehlo()
        if username:
            s.login(username, password)
        s.send_message(msg)


async def send_email(
    org: Organization,
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    """Build + dispatch an email. Raises SmtpNotConfigured / SmtpSendError on failure."""
    cfg = _resolve_config(org)
    from_email = str(cfg["from_email"])
    if not from_email:
        raise SmtpNotConfigured("SMTP from_email is not configured")

    msg = EmailMessage()
    from_name = str(cfg["from_name"])
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        await asyncio.to_thread(_send_blocking, cfg, msg)
    except smtplib.SMTPException as e:
        log.warning("smtp.send_failed", host=cfg["host"], to=to, error=str(e))
        raise SmtpSendError(str(e)) from e
    except OSError as e:
        log.warning("smtp.connect_failed", host=cfg["host"], to=to, error=str(e))
        raise SmtpSendError(f"connection failed: {e}") from e
