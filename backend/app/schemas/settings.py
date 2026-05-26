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
