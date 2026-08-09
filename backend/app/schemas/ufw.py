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


class UfwSuggestedRule(BaseModel):
    """The pre-filled fix the enable dialog offers."""

    action: str
    direction: str
    port: str | None
    protocol: str | None
    from_address: str | None
    comment: str | None


class UfwEnablePreflight(BaseModel):
    """What the enable dialog renders.

    Two distinct states, never one generic warning: a dialog that looks the
    same whether or not the host is safe teaches people to click through it.
    """

    already_active: bool
    # None when $SSH_CONNECTION was unavailable. The dialog then says the fix
    # cannot be pre-filled rather than guessing an address.
    management_address: str | None
    management_port: int | None
    default_incoming: str | None
    covered: bool
    covering_rule_spec: str | None
    covering_rule_summary: str | None
    suggested_rule: UfwSuggestedRule | None


class UfwSetEnabled(BaseModel):
    enabled: bool
    # Install the management rule in the same operation, immediately before
    # enabling. The offered fix.
    allow_management: bool = False
    # Proceed even though the pre-flight says the management path would not
    # survive. Audited distinctly from the safe path.
    force: bool = False


class UfwWriteResult(BaseModel):
    """What a guarded write did, and the guard that is watching it."""

    command: str
    guard: ChangeGuardPublic


class UfwDisabledRulePublic(BaseModel):
    """A rule switched off in NetFleet.

    It is not on the host and will not appear in `ufw status` there. The UI
    says so explicitly — anyone reading the host directly must not be misled
    by our screen into thinking these exist.
    """

    id: UUID
    spec: str
    position: int | None
    disabled_at: datetime
    # Parsed from the spec for display, so the table can show the same columns
    # as the live rules rather than a raw command line.
    action: str
    direction: str
    destination: str
    source: str
    interface: str | None = None
    comment: str | None = None


class UfwRuleToggle(BaseModel):
    spec: str = Field(min_length=5, max_length=512)
    force: bool = False


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
    # Rules NetFleet is holding off the host. Carried on the status response so
    # one fetch gives the whole picture — the enabled and the disabled halves
    # of a ruleset are only meaningful together.
    disabled_rules: list[UfwDisabledRulePublic] = []
