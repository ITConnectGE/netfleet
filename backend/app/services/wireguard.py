"""WireGuard helpers — keypair generation and client .conf assembly.

Pure functions; no side effects, no DB.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


@dataclass(slots=True)
class WgKeypair:
    private_b64: str
    public_b64: str


def generate_keypair() -> WgKeypair:
    """Generate a WireGuard X25519 keypair, base64-encoded per WG convention."""
    priv = X25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return WgKeypair(
        private_b64=base64.b64encode(priv_bytes).decode("ascii"),
        public_b64=base64.b64encode(pub_bytes).decode("ascii"),
    )


def generate_preshared_key() -> str:
    """32 random bytes, base64-encoded — RouterOS-compatible WG PSK."""
    import secrets

    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def build_client_config(
    *,
    client_private_key: str,
    client_address: str,
    client_dns: str | None,
    server_public_key: str,
    preshared_key: str | None,
    endpoint_host: str,
    endpoint_port: int,
    allowed_ips: str = "0.0.0.0/0, ::/0",
    persistent_keepalive: int | None = 25,
    mtu: int | None = None,
) -> str:
    """Produce a wg-quick(8) compatible .conf file as text."""
    iface_lines = [
        "[Interface]",
        f"PrivateKey = {client_private_key}",
        f"Address = {client_address}",
    ]
    if client_dns:
        iface_lines.append(f"DNS = {client_dns}")
    if mtu:
        iface_lines.append(f"MTU = {mtu}")

    peer_lines = [
        "",
        "[Peer]",
        f"PublicKey = {server_public_key}",
    ]
    if preshared_key:
        peer_lines.append(f"PresharedKey = {preshared_key}")
    peer_lines.append(f"AllowedIPs = {allowed_ips}")
    peer_lines.append(f"Endpoint = {endpoint_host}:{endpoint_port}")
    if persistent_keepalive:
        peer_lines.append(f"PersistentKeepalive = {persistent_keepalive}")

    return "\n".join(iface_lines + peer_lines) + "\n"
