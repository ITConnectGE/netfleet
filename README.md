<div align="center">

<img src="docs/assets/logo.svg" alt="NetFleet" width="160" />

# NetFleet

### Multi-vendor network fleet management for MSPs

**Open-source, self-hosted central management** for your routers, firewalls and edge
devices â€” with granular RBAC, delegated IT-support access, real-time monitoring,
in-app updates, and one-command Ubuntu install.

> **Shipping now**: MikroTik RouterOS driver. &nbsp;
> **Roadmap**: FortiGate Â· Cisco IOS-XE Â· Ubiquiti UISP Â· Aruba Â· MIST.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Made with FastAPI](https://img.shields.io/badge/Made%20with-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/UI-Next.js%2015-black.svg)](https://nextjs.org)
[![Docker](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED.svg)](https://docs.docker.com/compose/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[**Why NetFleet?**](#-why-netfleet) Â· [**Quick Start**](#-quick-start) Â· [**Features**](#-features) Â· [**Architecture**](#-architecture) Â· [**Roadmap**](#-roadmap) Â· [**Docs**](docs/)

<br/>

*An open-source project by* &nbsp; **[ITConnectGE](https://itconnectge.ge)** &nbsp; â€” built by MSP engineers, for MSP engineers.

</div>

---

## ðŸŽ¯ The Problem

If you run an IT outsourcing company, you probably manage **dozens to hundreds of network
devices across many client sites**, often from **multiple vendors** â€” MikroTik routers
at one client, FortiGate firewalls at another, a stray Cisco somewhere.

The tools you have all fall short:

- **WinBox / WebFig / FortiGate GUI / etc.** = one device at a time. Vendor silos.
- **The Dude / FortiManager / Cisco Prime** = vendor-locked. You need N tools.
- **Zabbix / LibreNMS** = monitoring only â€” you still SSH in to make changes.
- **Splynx / UISP** = ISP-billing platforms, not MSP fleet management.
- **Ansible / Salt** = great for engineers, terrible for L1 support staff.

**None of them let you say:**
> *"Junior support engineer Nika can read DHCP leases and edit NAT rules â€” only on
> Client A's MikroTik routers and Client B's FortiGate â€” and every action is logged."*

That's what **NetFleet** does.

## âœ¨ Why NetFleet?

|                                       | The Dude | Splynx | Zabbix | UISP | FortiManager | **NetFleet** |
|---------------------------------------|:---:|:---:|:---:|:---:|:---:|:---:|
| **Multi-vendor** central management   | âŒ  | âš ï¸  | âš ï¸  | âŒ  | âŒ  | âœ… |
| Central read **and write** management | âš ï¸  | âœ…  | âŒ  | âŒ  | âœ…  | âœ… |
| **Per-section** RBAC (DHCP / NAT / FW â€¦) | âŒ | âŒ  | âŒ  | âŒ  | âš ï¸  | âœ… |
| **Multi-client / multi-site** structure | âŒ | âœ…  | âš ï¸  | âŒ  | âš ï¸  | âœ… |
| Granular delegated **IT-support** access | âŒ | âŒ  | âŒ  | âŒ  | âš ï¸  | âœ… |
| Full **audit log** (who did what, where) | âŒ | âš ï¸  | âš ï¸  | âŒ  | âœ…  | âœ… |
| **Entra ID OIDC** + Local + TOTP      | âŒ  | âš ï¸  | âš ï¸  | âš ï¸  | âœ…  | âœ… |
| **In-app updates** (no SSH dance)     | âŒ  | âŒ  | âŒ  | âš ï¸  | âš ï¸  | âœ… |
| **Open Source** (Apache 2.0)          | âš ï¸  | âŒ  | âœ…  | âš ï¸  | âŒ  | âœ… |
| **Self-hosted**, one-command install  | âŒ  | âš ï¸  | âœ…  | âœ…  | âŒ  | âœ… |
| **Built for MSPs**                    | âŒ  | âš ï¸  | âŒ  | âŒ  | âš ï¸  | âœ… |

> âœ… = first-class Â· âš ï¸ = partial / awkward Â· âŒ = not supported

## ðŸš€ Features

### Authentication & access
- **Microsoft Entra ID (OIDC)** single sign-on with MFA
- **Local authentication** with Argon2 password hashing and TOTP (Authenticator, Authy, etc.)
- **JWT** access tokens + httpOnly refresh cookies

### Multi-vendor device fleet
- Plug-in **vendor driver** architecture â€” a single API surface across vendors
- **Site â†’ Device** hierarchy (one tenant = one MSP)
- Encrypted credential storage (Fernet, KEK from `.env`)
- Connection pooling with keepalives
- Real-time **status monitoring** (CPU, memory, uptime, link state)
- Historic metrics with 30-day retention

### Granular RBAC
- Roles scoped to **sites or specific devices**
- Permissions per **functional section** (`dhcp`, `firewall.nat`, `qos`, `vpn`, â€¦)
- **Read / write / execute** as separate verbs
- Casbin enforcer â€” policy-as-code, auditable

### Operations (MikroTik MVP)
- **DHCP** servers, leases, networks
- **IP / Firewall / NAT / Mangle** rules
- **Interfaces, addresses, routes, ARP, pools**
- **Queues** (simple + tree)
- **PPP** secrets, profiles
- **System**: identity, resource, clock, reboot, config backup
- **Tool**: ping, traceroute, fetch

### Platform
- **Audit log** of every action (user, device, section, payload, outcome, IP, UA)
- **In-app updates**: see when a new release is out, click Update, done â€” automatic pre-update DB backup and rollback on failure
- **Open REST API** with full OpenAPI / Swagger docs
- **WebSocket** push for real-time status
- **Webhooks** for integration with helpdesk / Slack / Teams

## ðŸ Quick Start

### One-command install (Ubuntu 22.04 / 24.04)

```bash
curl -fsSL https://raw.githubusercontent.com/ITConnectGE/netfleet/main/install.sh | sudo bash
```

The installer will:
1. Install Docker & Docker Compose if missing
2. Pull the latest `netfleet` images from `ghcr.io/itconnectge`
3. Generate secrets and write `/opt/netfleet/.env`
4. Start the stack and wait for healthchecks
5. Print the URL + initial setup token

Then open `https://your-server` and follow the setup wizard.

### Manual install (any Docker host)

```bash
git clone https://github.com/ITConnectGE/netfleet.git
cd netfleet
cp .env.example .env
# Edit .env â€” set secrets, OIDC config if you want SSO
docker compose up -d
```

### Configuration

All configuration is environment-variable driven â€” see [`.env.example`](.env.example).

Key sections:
- `NETFLEET_JWT_SECRET`, `NETFLEET_FERNET_KEY` â€” secrets (autogenerated by `install.sh`)
- `NETFLEET_OIDC_*` â€” Microsoft Entra ID (or any OIDC IdP) setup
- `NETFLEET_UPDATE_CHANNEL` â€” `stable` / `beta` / `manual`
- `NETFLEET_SMTP_*` â€” for invite emails & update notifications

## ðŸ— Architecture

```
                  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                  â”‚              Host: Ubuntu + Docker                â”‚
                  â”‚                                                    â”‚
  Admin â”€â”€â”€HTTPSâ”€â”€â”¼â”€â”€â–¶ caddy â”€â”¬â”€â”€â–¶ web (Next.js)                      â”‚
  IT Support      â”‚           â””â”€â”€â–¶ api (FastAPI + Casbin) â”€â”€â–¶ postgres â”‚
                  â”‚                  â”‚   â†‘       â†‘                     â”‚
                  â”‚                  â–¼   â”‚       â”‚                     â”‚
                  â”‚             vendor drivers   â–¼                     â”‚
                  â”‚           â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   redis                     â”‚
                  â”‚           â”‚ mikrotik â”‚                              â”‚
                  â”‚           â”‚ fortigateâ”‚  (cache + pubsub)           â”‚
                  â”‚           â”‚ cisco â€¦  â”‚                              â”‚
                  â”‚           â””â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”˜                              â”‚
                  â”‚                â”‚                                    â”‚
                  â”‚              worker          updater (docker.sock) â”‚
                  â”‚            (polling)         (in-app updates)      â”‚
                  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                   â”‚              â”‚
                          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â–¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                          â”‚  Device  â”‚   â”‚  ghcr.io + GitHub â”‚
                          â”‚  fleet   â”‚   â”‚  (image + releases)â”‚
                          â”‚ (multi-  â”‚   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚  vendor) â”‚
                          â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

ðŸ“ **Full architecture diagrams**: see [`docs/architecture.drawio`](docs/architecture.drawio)
(6 pages: system overview, Docker layout, auth flows, RBAC model, update flow, vendor-driver call flow).

## ðŸ”Œ Vendor Driver Model

NetFleet abstracts vendor differences behind a stable `VendorDriver` interface. Each device
declares its `vendor` field; the API routes calls through the matching driver:

```python
class VendorDriver(Protocol):
    async def connect(self, device: Device) -> Connection: ...
    async def system_info(self, conn) -> SystemInfo: ...
    async def dhcp_leases(self, conn) -> list[DhcpLease]: ...
    async def firewall_nat_list(self, conn) -> list[NatRule]: ...
    async def firewall_nat_add(self, conn, rule: NatRule) -> str: ...
    # ... per-section methods
    capabilities: set[Capability]  # what this driver supports
```

A driver only needs to implement the sections relevant to its platform. The UI auto-hides
sections that the active device's driver doesn't expose.

| Driver | Status | Library / API |
|---|---|---|
| **MikroTik (RouterOS 7.x)** | ðŸŸ¢ MVP â€” in active development | `librouteros` + REST fallback |
| **MikroTik (RouterOS 6.x)** | ðŸŸ¡ planned | legacy API |
| **FortiGate (FortiOS)** | ðŸ”µ roadmap | FortiOS REST API |
| **Cisco (IOS-XE / NX-OS)** | ðŸ”µ roadmap | RESTCONF / NETCONF |
| **Ubiquiti (UISP / UniFi)** | ðŸ”µ roadmap | UISP API |
| **Aruba / HPE** | ðŸ”µ roadmap | AOS-CX REST |

> Want to contribute a driver? See [`docs/vendor-drivers.md`](docs/vendor-drivers.md) (writing in progress).

## ðŸ” RBAC Philosophy â€” a concrete example

Say you have a junior support engineer "Nika" who should handle DHCP & NAT for Client A only.

```yaml
# In NetFleet UI: Settings â†’ Roles â†’ New Role
role: dhcp-nat-l1
scope:
  type: site
  id: client-a
permissions:
  - section: dhcp
    actions: [read, write]
  - section: firewall.nat
    actions: [read, write]
  - section: system.identity
    actions: [read]      # so Nika can see which device is which

# In Users â†’ Nika â†’ Assign role
user: nika@example.com
role: dhcp-nat-l1
```

Nika now sees only Client A's devices, only DHCP/NAT/identity tabs are visible,
and every action is recorded in the audit log with the request payload. She literally
**cannot** see other clients or other sections â€” the API rejects with 403 and audits the attempt.

The same policy works the same way whether Client A runs MikroTik or FortiGate; the
driver translates `firewall.nat` to the right vendor-native call.

## ðŸ§± Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **Python 3.12 Â· FastAPI** | Async, OpenAPI-native, Pydantic v2 |
| Vendor drivers | **Pluggable Protocol-based** | Add new vendors without touching API code |
| Authorization | **Casbin** | Policy-as-code RBAC with scopes |
| DB | **PostgreSQL 16** | RBAC ergonomics, JSONB audit, row-level security |
| Cache / Pub-sub | **Redis 7** | Status cache + WebSocket fan-out |
| Frontend | **Next.js 15 Â· shadcn/ui Â· Tailwind** | Polished, accessible, fast |
| Reverse proxy | **Caddy 2** | Auto HTTPS, zero config |
| Deploy | **Docker Compose** | One-command self-host |
| CI/CD | **GitHub Actions â†’ ghcr.io** | Free public images |

## ðŸ—º Roadmap

- [x] Phase 0 â€” Architecture & branding
- [ ] Phase 1 â€” **Skeleton** (Docker, FastAPI, Next.js, DB) â† *we are here*
- [ ] Phase 2 â€” Auth (local + TOTP + Entra OIDC)
- [ ] Phase 3 â€” Sites & devices CRUD + encrypted creds + connection test
- [ ] Phase 4 â€” RBAC engine + roles UI + audit log
- [ ] Phase 5 â€” **MikroTik driver** complete: DHCP, IP, Firewall/NAT, Interfaces, System
- [ ] Phase 6 â€” Real-time status (worker + WebSocket)
- [ ] Phase 7 â€” In-app updater + GitHub Releases integration
- [ ] Phase 8 â€” Audit UI, exports, webhooks
- [ ] **v1.0** â€” production-ready (MikroTik fully supported)
- [ ] Phase 9 â€” **FortiGate driver** (FortiOS REST)
- [ ] Phase 10 â€” Config backup/restore, scheduled jobs
- [ ] Future â€” Cisco IOS-XE driver, Ubiquiti driver, multi-tenant SaaS mode, OpenTelemetry, Grafana dashboards, Ansible-compatible export

See [open issues](https://github.com/ITConnectGE/netfleet/issues) for tracked work.

## ðŸ¤ Contributing

We welcome contributions â€” bug reports, PRs, docs, translations, **new vendor drivers**.

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md). All contributors agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## ðŸ“œ License

Apache License 2.0 â€” see [LICENSE](LICENSE). Patent grant included; safe for commercial and MSP-internal use.

## â¤ï¸ By ITConnectGE

NetFleet is built and maintained by **[ITConnectGE](https://itconnectge.ge)**, a Georgian IT
outsourcing company. We built it because we needed it ourselves â€” and we believe the MSP
community deserves an open, modern, vendor-agnostic alternative to expensive proprietary tools.

If NetFleet saves you time, â­ the repo, [tell us](https://github.com/ITConnectGE/netfleet/discussions), or contribute back.

---

<sub>MikroTikÂ® and RouterOSÂ® are registered trademarks of MikroTÄ«kls SIA. FortiGateÂ® is a registered trademark of Fortinet, Inc. CiscoÂ® is a registered trademark of Cisco Systems, Inc. NetFleet is an independent, community-driven project and is not affiliated with or endorsed by any of these companies. Vendor names are used solely for descriptive interoperability purposes.</sub>
