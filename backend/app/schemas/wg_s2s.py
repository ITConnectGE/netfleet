"""Site-to-site WireGuard tunnel wizard schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class S2SSide(BaseModel):
    """One half of the tunnel."""

    device_id: UUID
    interface_name: str = Field(min_length=1, max_length=64)
    # Address on the wg interface itself (e.g. "10.99.0.1/30").
    tunnel_cidr: str = Field(min_length=4, max_length=43)
    # LAN subnets this side will expose to the other side.
    expose_subnets: list[str] = Field(default_factory=list)


class S2SCreateRequest(BaseModel):
    a: S2SSide
    b: S2SSide
    # Side A is the listener. Side B dials in.
    listen_port: int = Field(default=51820, ge=1, le=65535)
    # Public endpoint that Device B will use to reach Device A (DDNS or
    # plain IP). The wizard pre-fills this from A's WAN list.
    public_endpoint: str = Field(min_length=1, max_length=255)
    # Single tag that goes into every comment so the operator can find
    # / revoke the whole tunnel in one shot.
    comment_tag: str = Field(min_length=1, max_length=64)

    open_firewall_on_a: bool = True
    create_forward_rules: bool = True
    persistent_keepalive: int = Field(default=25, ge=0, le=65535)


class S2SCreatedArtifact(BaseModel):
    """One thing the wizard wrote to a router; the operator can use it
    to find / revoke if a later step fails."""

    side: str  # "a" or "b"
    kind: str  # "interface" | "address" | "peer" | "filter"
    id: str | None
    detail: str | None = None


class S2SCreateResponse(BaseModel):
    comment_tag: str
    artifacts: list[S2SCreatedArtifact]
    # Public keys are echoed back so the operator can verify they match
    # what RouterOS shows on each device.
    public_key_a: str
    public_key_b: str
