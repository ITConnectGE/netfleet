from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChangeGuardPublic(BaseModel):
    """An armed (or resolved) dead-man timer protecting a firewall change."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID
    kind: str
    state: str
    window_seconds: int
    armed_at: datetime
    expires_at: datetime
    resolved_at: datetime | None = None
    detail: str | None = None


class UfwRulePublic(BaseModel):
    action: str
    direction: str
    destination: str
    source: str
    ip_version: str
    position: int | None = None
    position_v6: int | None = None
    interface: str | None = None
    app: str | None = None
    comment: str | None = None
    spec: str | None = None


class UfwRuleCreate(BaseModel):
    """A rule to install.

    Validation is deliberately duplicated in the driver
    (`_assert_safe_ufw_spec`): this layer gives the operator a readable error,
    that layer guarantees nothing malformed reaches the CLI regardless of
    which caller built it.
    """

    action: Literal["allow", "deny", "reject", "limit"] = "allow"
    direction: Literal["in", "out", "fwd"] = "in"
    from_address: str | None = Field(default=None, max_length=64)
    to_address: str | None = Field(default=None, max_length=64)
    port: str | None = Field(default=None, max_length=128)
    protocol: Literal["tcp", "udp"] | None = None
    interface: str | None = Field(default=None, max_length=16)
    comment: str | None = Field(default=None, max_length=255)
    # 1-based, matching `ufw insert`. Omit to append.
    position: int | None = Field(default=None, ge=1)


class UfwRuleDelete(BaseModel):
    """Delete by specification, never by position.

    ufw renumbers on every delete, so a position read when the page rendered
    can address a different rule by the time the request arrives. The spec
    comes back from `GET /firewall/ufw` on each rule.
    """

    spec: str = Field(min_length=5, max_length=512)
    # Overrides the "this is the only rule keeping NetFleet reachable" refusal.
    force: bool = False


class UfwRuleEdit(UfwRuleCreate):
    """Replace `spec` with the rule described by the inherited fields.

    Carries the original's specification rather than its number for the same
    reason a delete does: ufw renumbers constantly, a spec does not move.
    """

    spec: str = Field(min_length=5, max_length=512)
    force: bool = False


class UfwRuleMove(BaseModel):
    """Reorder a rule. ufw is first-match, so this changes behaviour even
    though nothing is added or removed."""

    spec: str = Field(min_length=5, max_length=512)
    position: int = Field(ge=1)
    force: bool = False


class UfwWriteResult(BaseModel):
    """What a guarded write did, and the guard that is watching it."""

    command: str
    guard: ChangeGuardPublic


class UfwStatusPublic(BaseModel):
    installed: bool
    active: bool
    logging: str | None = None
    default_incoming: str | None = None
    default_outgoing: str | None = None
    default_routed: str | None = None
    rules: list[UfwRulePublic] = []
    app_profiles: list[str] = []
    rules_from_added: bool = False
