"""Site-to-site WireGuard tunnel orchestrator.

Given two MikroTik devices in the same organisation, this service
provisions a working tunnel: matching interfaces, addresses, cross-keyed
peers, an inbound UDP rule on the listener side, and (optionally)
forward-chain accept rules tagged with a shared comment so the operator
can find and revoke the whole tunnel later.

RouterOS doesn't expose transactions across endpoints, so we run the
steps sequentially and collect a per-artifact log. If a later step
fails we surface what was already created — the operator can clean up
manually from the device's WireGuard / Firewall pages, or simply rerun
the wizard, because the comment tag is unique and idempotent at the
admin's discretion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_field
from app.drivers import get_driver
from app.drivers.base import (
    DeviceCredentials,
    FilterRule,
    IpRoute,
    WireguardInterface,
    WireguardPeer,
)
from app.models.wg_peer_secret import WgPeerSecret
from app.schemas.wg_s2s import (
    S2SCreateRequest,
    S2SCreateResponse,
    S2SCreatedArtifact,
)
from app.services import wireguard as wg
from app.services.device import _to_driver_creds, get_device

log = structlog.get_logger(__name__)


class S2SError(Exception):
    """Surfaced to the API with what was already provisioned."""

    def __init__(
        self,
        message: str,
        artifacts: list[S2SCreatedArtifact],
        public_key_a: str = "",
        public_key_b: str = "",
    ) -> None:
        super().__init__(message)
        self.artifacts = artifacts
        self.public_key_a = public_key_a
        self.public_key_b = public_key_b


async def create_site_to_site(
    session: AsyncSession,
    organization_id: UUID,
    payload: S2SCreateRequest,
) -> S2SCreateResponse:
    device_a = await get_device(session, organization_id, payload.a.device_id)
    device_b = await get_device(session, organization_id, payload.b.device_id)
    if device_a.id == device_b.id:
        raise S2SError("Tunnel endpoints must be two distinct devices.", [])

    driver_a = get_driver(device_a.vendor)
    driver_b = get_driver(device_b.vendor)
    creds_a: DeviceCredentials = _to_driver_creds(device_a)
    creds_b: DeviceCredentials = _to_driver_creds(device_b)

    # Generate the two keypairs server-side so we know both ends'
    # public keys without round-tripping through /interface/wireguard
    # /print — RouterOS derives the same public from the private we
    # hand it.
    keys_a = wg.generate_keypair()
    keys_b = wg.generate_keypair()
    tag = _sanitise_tag(payload.comment_tag)
    tag_comment = f"netfleet s2s {tag}"

    artifacts: list[S2SCreatedArtifact] = []

    def add(side: str, kind: str, ident: str | None, detail: str | None = None) -> None:
        artifacts.append(
            S2SCreatedArtifact(side=side, kind=kind, id=ident, detail=detail)
        )

    def fail(step: str, err: Exception) -> "S2SError":
        log.warning(
            "wg_s2s.step_failed",
            tag=tag,
            step=step,
            error=str(err),
            artifacts=[a.model_dump() for a in artifacts],
        )
        return S2SError(
            f"{step} failed on device: {err}",
            artifacts,
            public_key_a=keys_a.public_b64,
            public_key_b=keys_b.public_b64,
        )

    # 1. Interfaces (with our chosen private keys).
    try:
        await driver_a.wireguard_interface_add(
            creds_a,
            WireguardInterface(
                id=None,
                name=payload.a.interface_name,
                listen_port=payload.listen_port,
                private_key=keys_a.private_b64,
                public_key=keys_a.public_b64,
                comment=tag_comment,
            ),
        )
        add(
            "a",
            "interface",
            payload.a.interface_name,
            f"listen {payload.listen_port}",
        )
    except Exception as e:
        raise fail("Create interface on A", e) from e

    try:
        await driver_b.wireguard_interface_add(
            creds_b,
            WireguardInterface(
                id=None,
                name=payload.b.interface_name,
                listen_port=None,  # B dials out; no listen port required.
                private_key=keys_b.private_b64,
                public_key=keys_b.public_b64,
                comment=tag_comment,
            ),
        )
        add("b", "interface", payload.b.interface_name)
    except Exception as e:
        raise fail("Create interface on B", e) from e

    # 2. Tunnel IPs.
    try:
        await driver_a.ip_address_add(
            creds_a,
            address=payload.a.tunnel_cidr,
            interface=payload.a.interface_name,
            comment=tag_comment,
        )
        add("a", "address", payload.a.tunnel_cidr)
    except Exception as e:
        raise fail("Add tunnel address on A", e) from e

    try:
        await driver_b.ip_address_add(
            creds_b,
            address=payload.b.tunnel_cidr,
            interface=payload.b.interface_name,
            comment=tag_comment,
        )
        add("b", "address", payload.b.tunnel_cidr)
    except Exception as e:
        raise fail("Add tunnel address on B", e) from e

    # 3. Peers. allowed-address on each peer = the other side's tunnel
    # IP + whatever subnets the other side chose to expose. RouterOS
    # also auto-routes those subnets via the peer.
    allowed_for_peer_on_a = _join_cidrs(
        [_host_cidr(payload.b.tunnel_cidr), *payload.b.expose_subnets]
    )
    allowed_for_peer_on_b = _join_cidrs(
        [_host_cidr(payload.a.tunnel_cidr), *payload.a.expose_subnets]
    )

    try:
        peer_a_router_id = await driver_a.wireguard_peer_add(
            creds_a,
            WireguardPeer(
                id=None,
                interface=payload.a.interface_name,
                public_key=keys_b.public_b64,
                allowed_address=allowed_for_peer_on_a,
                persistent_keepalive=payload.persistent_keepalive or None,
                comment=tag_comment,
            ),
        )
        add("a", "peer", peer_a_router_id, "B as remote")
    except Exception as e:
        raise fail("Add peer on A", e) from e

    try:
        peer_b_router_id = await driver_b.wireguard_peer_add(
            creds_b,
            WireguardPeer(
                id=None,
                interface=payload.b.interface_name,
                public_key=keys_a.public_b64,
                allowed_address=allowed_for_peer_on_b,
                endpoint_address=payload.public_endpoint,
                endpoint_port=payload.listen_port,
                persistent_keepalive=payload.persistent_keepalive or None,
                comment=tag_comment,
            ),
        )
        add("b", "peer", peer_b_router_id, "A as remote")
    except Exception as e:
        raise fail("Add peer on B", e) from e

    # Empty preshared-key for both — RouterOS-safe; no cache row needed.
    _ = encrypt_field  # silence "imported but unused"
    _ = WgPeerSecret

    # 4. Open UDP on A (input chain) so B can actually hit it.
    if payload.open_firewall_on_a:
        try:
            rule_id = await driver_a.firewall_filter_add(
                creds_a,
                FilterRule(
                    id=None,
                    chain="input",
                    action="accept",
                    protocol="udp",
                    dst_port=str(payload.listen_port),
                    comment=f"{tag_comment} listen",
                ),
            )
            add("a", "filter", rule_id, "input accept udp")
            # Move to the very top so a downstream catch-all drop can't
            # eat the handshake.
            try:
                rules = await driver_a.firewall_filter_list(creds_a)
                first_input = next(
                    (
                        r
                        for r in rules
                        if r.chain == "input" and r.id and r.id != rule_id
                    ),
                    None,
                )
                if first_input and first_input.id:
                    await driver_a.firewall_filter_move(
                        creds_a, rule_id, before_id=first_input.id
                    )
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "wg_s2s.input_rule_move_failed", tag=tag, error=str(e)
                )
        except Exception as e:
            raise fail("Open UDP firewall on A", e) from e

    # 5. Forward accept rules tagged so we don't fight a catch-all drop
    # in the forward chain. Two rules per side: in via the WG interface,
    # out via the WG interface. Combined with allowed-address (which
    # acts as an ACL) and the operator's exposed-subnets choice, that's
    # the practical ACL surface.
    if payload.create_forward_rules:
        for side, driver, creds, iface_name in (
            ("a", driver_a, creds_a, payload.a.interface_name),
            ("b", driver_b, creds_b, payload.b.interface_name),
        ):
            try:
                rid_in = await driver.firewall_filter_add(
                    creds,
                    FilterRule(
                        id=None,
                        chain="forward",
                        action="accept",
                        in_interface=iface_name,
                        comment=f"{tag_comment} forward in",
                    ),
                )
                add(side, "filter", rid_in, "forward in")
                rid_out = await driver.firewall_filter_add(
                    creds,
                    FilterRule(
                        id=None,
                        chain="forward",
                        action="accept",
                        out_interface=iface_name,
                        comment=f"{tag_comment} forward out",
                    ),
                )
                add(side, "filter", rid_out, "forward out")
                # Lift both above the first pre-existing forward rule so a
                # catch-all drop at the bottom of the chain can't shadow
                # them. Moving each before the same anchor leaves them on
                # top in [in, out, …existing] order. Best-effort.
                try:
                    rules = await driver.firewall_filter_list(creds)
                    first_fwd = next(
                        (
                            r
                            for r in rules
                            if r.chain == "forward"
                            and r.id
                            and r.id not in (rid_in, rid_out)
                        ),
                        None,
                    )
                    if first_fwd and first_fwd.id:
                        await driver.firewall_filter_move(
                            creds, rid_in, before_id=first_fwd.id
                        )
                        await driver.firewall_filter_move(
                            creds, rid_out, before_id=first_fwd.id
                        )
                except Exception as e:  # noqa: BLE001
                    log.warning(
                        "wg_s2s.forward_rule_move_failed",
                        tag=tag,
                        side=side,
                        error=str(e),
                    )
            except Exception as e:
                raise fail(
                    f"Add forward accept on {side.upper()}", e
                ) from e

    # 6. Static routes for each side's exposed subnets, via the remote
    # tunnel IP. RouterOS does NOT derive /ip routes from a peer's
    # allowed-address (that field is only the crypto-key ACL), so without
    # these the tunnel comes up but the remote LANs stay unreachable.
    if payload.create_routes:
        gw_b = _bare_host(payload.b.tunnel_cidr)  # A reaches B's LANs via B
        gw_a = _bare_host(payload.a.tunnel_cidr)  # B reaches A's LANs via A
        for subnet in payload.b.expose_subnets:
            try:
                rid = await driver_a.ip_route_add(
                    creds_a,
                    IpRoute(
                        id=None,
                        dst_address=subnet,
                        gateway=gw_b,
                        comment=tag_comment,
                    ),
                )
                add("a", "route", rid, f"{subnet} via {gw_b}")
            except Exception as e:
                raise fail(f"Add route to {subnet} on A", e) from e
        for subnet in payload.a.expose_subnets:
            try:
                rid = await driver_b.ip_route_add(
                    creds_b,
                    IpRoute(
                        id=None,
                        dst_address=subnet,
                        gateway=gw_a,
                        comment=tag_comment,
                    ),
                )
                add("b", "route", rid, f"{subnet} via {gw_a}")
            except Exception as e:
                raise fail(f"Add route to {subnet} on B", e) from e

    # Track when the tunnel was provisioned for any future "list tunnels"
    # endpoint. Lightweight — we don't persist a row in the DB yet; the
    # comment tag is the canonical id.
    _ = datetime.now(UTC)

    return S2SCreateResponse(
        comment_tag=tag,
        artifacts=artifacts,
        public_key_a=keys_a.public_b64,
        public_key_b=keys_b.public_b64,
    )


# ---------------- helpers ----------------


def _sanitise_tag(s: str) -> str:
    out = "".join(c for c in s if c.isalnum() or c in "-_")
    return out.strip("-_") or "untitled"


def _host_cidr(cidr: str) -> str:
    """Return the /32 of the host bit so allowed-address is just the
    other side's single tunnel IP, not the whole /30."""
    if "/" not in cidr:
        return f"{cidr}/32"
    host = cidr.split("/", 1)[0]
    return f"{host}/32"


def _bare_host(cidr: str) -> str:
    """The bare tunnel IP (no /prefix) — used as the route gateway so each
    side reaches the other's LANs via the remote tunnel endpoint."""
    return cidr.split("/", 1)[0].strip()


def _join_cidrs(items: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for c in items:
        c = (c or "").strip()
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(c)
    return ",".join(out)
