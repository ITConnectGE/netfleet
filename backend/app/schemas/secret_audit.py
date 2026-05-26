from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.secret_audit import SecretKind


class RevealRequest(BaseModel):
    """Required body for any secret-reveal endpoint."""

    justification: str | None = Field(default=None, max_length=1024)


class UnrotatedSecretPublic(BaseModel):
    device_id: UUID
    device_name: str
    secret_kind: SecretKind
    secret_identifier: str
    secret_label: str | None
    revealed_at: datetime
    last_rotated_at: datetime | None


class RiskReport(BaseModel):
    user_id: UUID
    count: int
    items: list[UnrotatedSecretPublic]


class RevealedPppSecret(BaseModel):
    secret_identifier: str
    name: str
    service: str
    password: str


class RevealedWireguardKeys(BaseModel):
    peer_id: str
    public_key: str | None
    preshared_key: str | None
