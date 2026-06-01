from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SmtpSettingsPublic(BaseModel):
    """SMTP config visible to admins. Never returns the raw password."""

    smtp_enabled: bool
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_from_email: str | None
    smtp_from_name: str | None
    smtp_use_tls: bool
    smtp_use_starttls: bool
    has_smtp_password: bool

    model_config = {"from_attributes": True}


class SmtpSettingsUpdate(BaseModel):
    """All fields optional — partial updates supported. Set smtp_password to '' to clear."""

    smtp_enabled: bool | None = None
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=512)
    smtp_from_email: EmailStr | None = None
    smtp_from_name: str | None = Field(default=None, max_length=255)
    smtp_use_tls: bool | None = None
    smtp_use_starttls: bool | None = None


class SmtpTestRequest(BaseModel):
    to: EmailStr


class SmtpTestResult(BaseModel):
    ok: bool
    error: str | None = None


# ---------------- SMS gateway ----------------


class SmsSettingsPublic(BaseModel):
    sms_enabled: bool
    sms_provider: str
    sms_api_url: str | None
    sms_http_method: str
    sms_body_format: str
    sms_body_template: str | None
    sms_auth_header_name: str | None
    sms_auth_header_value_template: str | None
    sms_sender: str | None
    sms_success_status_min: int
    sms_success_status_max: int
    sms_success_body_contains: str | None
    sms_timeout_seconds: int
    has_sms_api_key: bool
    sms_last_test_at: object | None  # datetime, but JSON-friendly
    sms_last_test_ok: bool | None
    sms_last_test_message: str | None

    model_config = {"from_attributes": True}


class SmsSettingsUpdate(BaseModel):
    sms_enabled: bool | None = None
    sms_provider: str | None = Field(default=None, max_length=32)
    sms_api_url: str | None = Field(default=None, max_length=2048)
    sms_http_method: str | None = Field(default=None, max_length=8)
    sms_body_format: str | None = Field(default=None, max_length=16)
    sms_body_template: str | None = Field(default=None, max_length=4096)
    sms_auth_header_name: str | None = Field(default=None, max_length=64)
    sms_auth_header_value_template: str | None = Field(default=None, max_length=256)
    sms_api_key: str | None = Field(default=None, max_length=512)
    sms_sender: str | None = Field(default=None, max_length=32)
    sms_success_status_min: int | None = Field(default=None, ge=100, le=599)
    sms_success_status_max: int | None = Field(default=None, ge=100, le=599)
    sms_success_body_contains: str | None = Field(default=None, max_length=128)
    sms_timeout_seconds: int | None = Field(default=None, ge=1, le=120)


class SmsTestRequest(BaseModel):
    to: str = Field(min_length=4, max_length=32)
    content: str = Field(default="NetFleet SMS test", min_length=1, max_length=160)


class SmsTestResult(BaseModel):
    ok: bool
    http_status: int | None = None
    response_body: str | None = None
    error: str | None = None


class OrgInfoPublic(BaseModel):
    """Org-wide miscellaneous settings — currently just NetFleet's external IPs."""

    netfleet_external_ips: str | None

    model_config = {"from_attributes": True}


class OrgInfoUpdate(BaseModel):
    netfleet_external_ips: str | None = Field(default=None, max_length=512)


class SmsProviderPreset(BaseModel):
    key: str
    label: str
    api_url: str
    http_method: str
    body_format: str
    body_template: str
    auth_header_name: str | None = None
    auth_header_value_template: str | None = None
    success_status_min: int = 200
    success_status_max: int = 299
    success_body_contains: str | None = None
    notes: str | None = None


# ---------------- Authorization (OIDC + MFA toggles) ----------------


class AuthSettingsPublic(BaseModel):
    """Org-wide authorization config exposed to admins. Client secrets
    are never returned in plaintext — only a `has_*_secret` boolean."""

    microsoft_oidc_enabled: bool
    microsoft_oidc_tenant_id: str | None
    microsoft_oidc_client_id: str | None
    has_microsoft_oidc_client_secret: bool

    google_oidc_enabled: bool
    google_oidc_client_id: str | None
    has_google_oidc_client_secret: bool

    mfa_totp_enabled: bool
    mfa_sms_otp_enabled: bool
    mfa_email_otp_enabled: bool

    # Convenience: the redirect/callback URLs the admin must paste into
    # the IdP console. Built from PUBLIC_URL on the server so the UI
    # doesn't have to know where the API lives.
    microsoft_redirect_uri: str
    google_redirect_uri: str

    model_config = {"from_attributes": True}


class AuthSettingsUpdate(BaseModel):
    """All fields optional — partial updates supported. Set the
    `*_client_secret` fields to '' to clear them."""

    microsoft_oidc_enabled: bool | None = None
    microsoft_oidc_tenant_id: str | None = Field(default=None, max_length=128)
    microsoft_oidc_client_id: str | None = Field(default=None, max_length=255)
    microsoft_oidc_client_secret: str | None = Field(default=None, max_length=512)

    google_oidc_enabled: bool | None = None
    google_oidc_client_id: str | None = Field(default=None, max_length=255)
    google_oidc_client_secret: str | None = Field(default=None, max_length=512)

    mfa_totp_enabled: bool | None = None
    mfa_sms_otp_enabled: bool | None = None
    mfa_email_otp_enabled: bool | None = None
