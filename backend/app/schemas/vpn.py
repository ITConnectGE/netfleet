from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------- PPP secrets (L2TP / PPTP / SSTP / OVPN) ----------------


class PppSecretPublic(BaseModel):
    id: str | None
    name: str
    service: str
    profile: str | None
    local_address: str | None
    remote_address: str | None
    disabled: bool
    comment: str | None


class PppSecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    service: str = Field(default="any", max_length=32)
    password: str = Field(min_length=1, max_length=512)
    profile: str | None = Field(default=None, max_length=64)
    local_address: str | None = Field(default=None, max_length=64)
    remote_address: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=255)


class PppSecretPasswordReset(BaseModel):
    new_password: str = Field(min_length=1, max_length=512)


# ---------------- WireGuard ----------------


class WireguardInterfacePublic(BaseModel):
    id: str | None
    name: str
    listen_port: int | None
    public_key: str | None
    mtu: int | None
    disabled: bool
    comment: str | None


class WireguardInterfaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    listen_port: int | None = Field(default=None, ge=1, le=65535)
    private_key: str | None = Field(default=None, max_length=512)
    mtu: int | None = Field(default=None, ge=576, le=9000)
    comment: str | None = Field(default=None, max_length=255)


class WireguardPeerPublic(BaseModel):
    id: str | None
    interface: str
    public_key: str | None
    allowed_address: str | None
    endpoint_address: str | None
    endpoint_port: int | None
    persistent_keepalive: int | None
    disabled: bool
    comment: str | None


class WireguardPeerCreate(BaseModel):
    interface: str = Field(min_length=1, max_length=64)
    # Optional: when omitted NetFleet mints the keypair server-side, puts the
    # public half on the router peer and returns the private half once so the
    # caller can assemble a working client .conf.
    public_key: str | None = Field(default=None, max_length=512)
    preshared_key: str | None = Field(default=None, max_length=512)
    allowed_address: str | None = Field(default=None, max_length=255)
    endpoint_address: str | None = Field(default=None, max_length=255)
    endpoint_port: int | None = Field(default=None, ge=1, le=65535)
    persistent_keepalive: int | None = Field(default=None, ge=0, le=65535)
    comment: str | None = Field(default=None, max_length=255)


class WireguardPeerConfigRequest(BaseModel):
    """Client-side fields needed to assemble a .conf file. RouterOS stores some
    of these (server pub key, allowed_address) but not the client-facing
    endpoint or DNS — those come from the admin at download time.
    """

    server_endpoint: str = Field(min_length=1, max_length=255, description="DNS or IP of the WG server")
    server_endpoint_port: int = Field(ge=1, le=65535)
    # Private half of the peer's keypair, when NetFleet minted it at create
    # time. Passing it here makes the .conf's PrivateKey match the public key
    # on the router. Omit for client-owned keypairs (a placeholder is emitted).
    client_private_key: str | None = Field(default=None, max_length=512)
    client_address: str = Field(description="The IP/subnet the client will use, e.g. 10.10.10.5/24")
    client_dns: str | None = Field(default="1.1.1.1", max_length=128)
    allowed_ips: str = Field(default="0.0.0.0/0", description="What traffic to tunnel; usually 0.0.0.0/0")
    persistent_keepalive: int | None = Field(default=25, ge=0, le=65535)
