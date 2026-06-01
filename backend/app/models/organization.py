from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import IdMixin, TableNameMixin, TimestampsMixin

if TYPE_CHECKING:
    from app.models.user import User


class Organization(IdMixin, TimestampsMixin, TableNameMixin, Base):
    """The MSP itself. Single-tenant per deployment, but modeled as 1 row for future SaaS mode."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False, index=True)
    is_setup_complete: Mapped[bool] = mapped_column(default=False, nullable=False)

    # SMTP — credentials encrypted at rest via app.core.security.encrypt_field
    smtp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    smtp_host: Mapped[str | None] = mapped_column(String(255))
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str | None] = mapped_column(String(255))
    smtp_password_encrypted: Mapped[str | None] = mapped_column(String(1024))
    smtp_from_email: Mapped[str | None] = mapped_column(String(254))
    smtp_from_name: Mapped[str | None] = mapped_column(String(255))
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    smtp_use_starttls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # SMS gateway — generic HTTP webhook config + per-provider presets.
    # The body / header templates use {key} {sender} {destination} {content}
    # placeholders so the same plumbing works for smsoffice.ge, Twilio,
    # in-house Kannel deployments, etc. without code changes.
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sms_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="custom")
    sms_api_url: Mapped[str | None] = mapped_column(Text)
    sms_http_method: Mapped[str] = mapped_column(String(8), nullable=False, default="POST")
    sms_body_format: Mapped[str] = mapped_column(String(16), nullable=False, default="form")
    sms_body_template: Mapped[str | None] = mapped_column(Text)
    sms_auth_header_name: Mapped[str | None] = mapped_column(String(64))
    sms_auth_header_value_template: Mapped[str | None] = mapped_column(String(256))
    sms_api_key_encrypted: Mapped[str | None] = mapped_column(String(1024))
    sms_sender: Mapped[str | None] = mapped_column(String(32))
    sms_success_status_min: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    sms_success_status_max: Mapped[int] = mapped_column(Integer, nullable=False, default=299)
    sms_success_body_contains: Mapped[str | None] = mapped_column(String(128))
    sms_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    sms_last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sms_last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    sms_last_test_message: Mapped[str | None] = mapped_column(Text)

    # NetFleet's own egress IP(s), as seen by managed devices. Used to fill
    # the whitelist in the device-onboarding script (also persists across
    # support staff onboarding new clients). Comma-separated, IPs or CIDRs.
    netfleet_external_ips: Mapped[str | None] = mapped_column(Text)

    # --- Authorization: external IdPs (per-org Microsoft / Google OIDC) ---
    # Tenant id can be a UUID, "common", "organizations", or "consumers"
    # (Microsoft Entra terminology); empty means "common" by default.
    microsoft_oidc_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    microsoft_oidc_tenant_id: Mapped[str | None] = mapped_column(String(128))
    microsoft_oidc_client_id: Mapped[str | None] = mapped_column(String(255))
    microsoft_oidc_client_secret_encrypted: Mapped[str | None] = mapped_column(String(1024))

    google_oidc_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    google_oidc_client_id: Mapped[str | None] = mapped_column(String(255))
    google_oidc_client_secret_encrypted: Mapped[str | None] = mapped_column(String(1024))

    # --- Authorization: org-wide MFA factor toggles ---
    # When the admin turns a factor off here, the corresponding per-user
    # enrollment / dispatch path returns 503. Existing enrollments aren't
    # deleted — flipping the toggle back on restores them.
    mfa_totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mfa_sms_otp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mfa_email_otp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    users: Mapped[list[User]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
