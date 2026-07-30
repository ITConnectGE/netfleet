<div align="center">

<img src="docs/assets/logo.svg" alt="NetFleet" width="160" />

# NetFleet

### Multi-vendor network fleet management for MSPs

**Open-source, self-hosted central management** for your routers, firewalls, edge
devices **and Linux servers** - with granular RBAC, delegated IT-support access,
real-time monitoring, in-app updates, and one-command Ubuntu install.

> **Shipping now**: MikroTik RouterOS driver (RouterOS 6.x and 7.x).
> **In development**: [Linux server driver](docs/LINUX-PLAN.md) - agentless SSH, for
> cloud VPS fleets.
> **Roadmap**: FortiGate, Cisco IOS-XE, Ubiquiti UISP, Aruba, MIST.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Made with FastAPI](https://img.shields.io/badge/Made%20with-FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/UI-Next.js%2015-black.svg)](https://nextjs.org)
[![Docker](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED.svg)](https://docs.docker.com/compose/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[**Why NetFleet?**](#why-netfleet) - [**Quick Start**](#quick-start) - [**Features**](#features) - [**Architecture**](#architecture) - [**Roadmap**](#roadmap) - [**Docs**](docs/)

<br/>

*An open-source project by* &nbsp; **[ITConnect](https://itconnect.ge)** &nbsp; - built by MSP engineers, for MSP engineers.

</div>

---

## The Problem

If you run an IT outsourcing company, you probably manage **dozens to hundreds of network
devices across many client sites**, often from **multiple vendors** - MikroTik routers
at one client, FortiGate firewalls at another, a stray Cisco somewhere.

And that is only the network half. The other half is **Linux servers - both in the
cloud and on the internal network**. A handful of VPSes at Hetzner, a few at
DigitalOcean, plus the file server, the hypervisor and the monitoring box sitting in
a client's own LAN. Each one its own SSH session, its own patch level, its own firewall.

The tools you have all fall short:

- **WinBox / WebFig / FortiGate GUI / etc.** = one device at a time. Vendor silos.
- **The Dude / FortiManager / Cisco Prime** = vendor-locked. You need N tools.
- **Zabbix / LibreNMS** = monitoring only - you still SSH in to make changes.
- **Splynx / UISP** = ISP-billing platforms, not MSP fleet management.
- **Ansible / Salt** = great for engineers, terrible for L1 support staff.

**None of them let you say:**
> *"Junior support engineer Nika can read DHCP leases and edit NAT rules - only on
> Client A's MikroTik routers and Client B's FortiGate - and every action is logged."*

That's what **NetFleet** does.

## Why NetFleet?

|                                       | The Dude | Splynx | Zabbix | UISP | FortiManager | **NetFleet** |
|---------------------------------------|:---:|:---:|:---:|:---:|:---:|:---:|
| **Multi-vendor** central management   | no  | partial | partial | no  | no  | yes |
| Central read **and write** management | partial | yes  | no  | no  | yes  | yes |
| **Per-section** RBAC (DHCP / NAT / FW ...) | no | no  | no  | no  | partial | yes |
| **Multi-tenant + multi-site** structure | no | yes  | partial | no  | partial | yes |
| Granular delegated **IT-support** access | no | no  | no  | no  | partial | yes |
| Full **audit log** (who did what, where) | no | partial | partial | no  | yes  | yes |
| **Entra ID OIDC** + Local + TOTP      | no  | partial | partial | partial | yes  | yes |
| **In-app updates** (no SSH dance)     | no  | no  | no  | partial | partial | yes |
| **Open Source** (Apache 2.0)          | partial | no  | yes  | partial | no  | yes |
| **Self-hosted**, one-command install  | no  | partial | yes  | yes  | no  | yes |
| **Built for MSPs**                    | no  | partial | no  | no  | partial | yes |

## Features

### Authentication and access

- **Microsoft Entra ID (OIDC)** single sign-on with MFA
- **Local authentication** with Argon2 password hashing and TOTP (Authenticator, Authy, etc.)
- **JWT** access tokens + refresh-token rotation with reuse detection

### Multi-vendor device fleet

- Plug-in **vendor driver** architecture - a single API surface across vendors
- **Organization -> Tenant (client) -> Site -> Device** hierarchy
- Encrypted credential storage (Fernet, KEK from `.env`)
- Real-time **status monitoring** (CPU, memory, uptime, link state)
- CDP / LLDP / MNDP neighbour discovery per device

### Granular RBAC

- Roles scoped to **organization, tenant, site, or specific device**
- Permissions per **functional section** (`dhcp`, `firewall.nat`, `queue.simple`, `vpn.l2tp`, ...)
- **Read / write / execute** as separate verbs
- Direct Python enforcer - plain SQL rows you can inspect and `git diff`

### Operations (MikroTik MVP)

- **DHCP** servers, leases, networks
- **IP / Firewall / NAT / Mangle** rules
- **Interfaces, addresses, routes, ARP, bridge hosts, VLANs**
- **Queues** (simple + tree, quota limits)
- **PPP secrets** (L2TP / PPTP / SSTP / OVPN) with secret-reveal audit
- **WireGuard** interfaces, peers, config download with keys
- **NTP** client + server + device clock view
- **SNMP** enable + communities
- **IP services** (api, ssh, www, winbox, ...) with editable bind-address whitelist
- **Device users** with bulk password reset
- **Firewall filter** CRUD + RouterOS log viewer
- **System**: identity, resource, clock, backup, firmware check + upgrade
- Daily scheduled backups (SFTP-pulled to NetFleet) with retention + on-demand restore
- Firmware: nightly fleet-wide update check, per-device upgrade trigger,
  per-device auto-upgrade window (UTC hour range)

### Linux and cloud VPS fleet (in development - see [LINUX-PLAN.md](docs/LINUX-PLAN.md))

Your servers do not live in one place. Some are scattered across Hetzner, DigitalOcean,
Contabo, AWS and that one VPS nobody remembers paying for. The rest sit **inside your
clients' internal networks** - file servers, hypervisors, database boxes, the Zabbix VM,
appliances with no public IP at all. Today that means N SSH sessions, N tmux panes, and
no idea which box is three kernel CVEs behind.

NetFleet treats a Linux host as just another device in the same fleet as your routers -
same tenant/site hierarchy, same RBAC, same audit log:

- **Agentless.** Nothing is installed on your servers. Pure SSH, key or password auth,
  unprivileged user + `sudo`. Works on any host the moment you can SSH into it -
  no ports to open, no agent to keep updated, no vendor lock-in.
- **Cloud and internal alike.** A public VPS and a `10.0.0.x` file server behind a
  client's router are the same kind of device here. Internal hosts need no public IP
  and no inbound port-forward - NetFleet reaches them the same way you already do,
  over your management network or the WireGuard tunnel it set up on the router.
- **One command, every server, at once.** Select 40 hosts across 6 providers, run the
  command, get per-host exit codes and output in one view. Free-form execution is
  behind its own permission that no default role holds; a curated safe-command
  catalog covers day-to-day L1 work.
- **All your alerts on one screen.** Failed systemd units, disks near full, pending
  security updates, reboot-required flags, journald errors - aggregated across the
  whole fleet instead of hidden inside each box.
- **Firewall management.** nftables rules read and edited from the UI, with a
  mandatory lockout guard: every ruleset change is applied behind a rollback timer
  and reverts itself unless you explicitly confirm you still have access.
- **Patch management.** Nightly fleet-wide scan for pending package updates
  (security count broken out), one-click or scheduled upgrades inside a maintenance
  window - reusing the same machinery as router firmware upgrades.
- **Services, storage, processes, users.** systemd unit control, disk and inode usage,
  top processes, host accounts and `authorized_keys` - all RBAC-scoped and audited.
- **Backups.** `/etc` archive plus a package manifest, on the same schedule and
  retention policy as your router backups.
- **WireGuard.** A Linux host can be a site-to-site tunnel endpoint, so
  Linux <-> MikroTik tunnels are built from the same UI.

Because it is the same RBAC engine, a role like *"restart services and read logs on
Client A's web servers only"* works exactly like *"edit NAT on Client A's routers only"*.

### Platform

- **Audit log** of every action (user, device, section, payload, outcome, IP, UA)
  with automatic secret redaction
- **Reports**: user activity, device activity, secret access (with
  offboarding-risk: reveals not rotated since), change log - all exportable as CSV
- **In-app updates**: see when a new release is out, click Update, done -
  automatic pre-update `pg_dump` and version-tag persistence
- **Open REST API** with full OpenAPI / Swagger docs

## Quick Start

### One-command install (Ubuntu 22.04 / 24.04)

```bash
curl -fsSL https://raw.githubusercontent.com/ITConnectGE/netfleet/main/install.sh | sudo bash
```

The installer will:

1. Install Docker and Docker Compose if missing
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
# Edit .env - set secrets, OIDC config if you want SSO
docker compose up -d
```

### Configuration

All configuration is environment-variable driven - see [`.env.example`](.env.example).

Key sections:

- `NETFLEET_JWT_SECRET`, `NETFLEET_FERNET_KEY` - secrets (autogenerated by `install.sh`)
- `NETFLEET_OIDC_*` - Microsoft Entra ID (or any OIDC IdP) setup
- `NETFLEET_UPDATE_CHANNEL` - `stable` / `beta` / `manual`
- `NETFLEET_SMTP_*` - for invite emails and update notifications

## Architecture

```
                  +---------------------------------------------------+
                  |              Host: Ubuntu + Docker                |
                  |                                                   |
  Admin -----HTTPS-->  caddy -+--> web (Next.js)                      |
  IT Support      |           +--> api (FastAPI) ----------> postgres |
                  |                  |     ^      ^                   |
                  |                  v     |      |                   |
                  |             vendor drivers    v                   |
                  |           +---------------+   redis               |
                  |           | mikrotik      |                       |
                  |           | fortigate ... |  (cache + pubsub)     |
                  |           +-------+-------+                       |
                  |                   |                               |
                  |                worker         updater (docker.sock)
                  |              (scheduler)      (in-app updates)    |
                  +-------------------+--------------+----------------+
                                      |              |
                             +--------v--+    +------v------------+
                             |  Device   |    |  ghcr.io + GitHub |
                             |  fleet    |    | (images, releases)|
                             | (multi-   |    +-------------------+
                             |  vendor)  |
                             +-----------+
```

- **caddy** terminates TLS (auto Let's Encrypt) and reverse-proxies `/api` to
  the FastAPI service and everything else to the Next.js front-end.
- **api** owns RBAC, vendor-driver dispatch, audit log, and the REST surface.
- **worker** runs scheduled jobs: nightly backups + retention, daily firmware
  checks, hourly auto-upgrade window scan.
- **updater** is a small isolated service with the Docker socket; it polls
  GitHub Releases, runs `docker compose pull` + recreate for the other services,
  and self-excludes from the recreate so it can keep running across updates.

## Vendor Driver Model

NetFleet abstracts vendor differences behind a stable `VendorDriver` interface.
Each device declares its `vendor` field; the API routes calls through the
matching driver:

```python
class VendorDriver(Protocol):
    vendor: str
    display_name: str
    capabilities: set[Capability]

    async def test_connection(self, creds: DeviceCredentials) -> bool: ...
    async def system_info(self, creds: DeviceCredentials) -> SystemInfo: ...
    async def dhcp_leases(self, creds: DeviceCredentials) -> list[DhcpLease]: ...
    async def firewall_filter_list(self, creds: DeviceCredentials) -> list[FilterRule]: ...
    # ... 30+ per-section methods, each optional via `capabilities`
```

A driver only needs to implement the sections relevant to its platform. The UI
auto-hides sections that the active device's driver does not expose.

| Driver | Status | Library / API |
|---|---|---|
| **MikroTik (RouterOS 7.x)** | shipped | `librouteros` (API) + paramiko (SFTP) |
| **MikroTik (RouterOS 6.x)** | shipped | same driver, both ROS majors |
| **Linux (Debian / Ubuntu / RHEL / Rocky)** | in development | agentless SSH (paramiko), `ip -j` / systemd / nftables |
| **FortiGate (FortiOS)**     | roadmap | FortiOS REST API |
| **Cisco (IOS-XE / NX-OS)**  | roadmap | RESTCONF / NETCONF |
| **Ubiquiti (UISP / UniFi)** | roadmap | UISP API |
| **Aruba / HPE**             | roadmap | AOS-CX REST |

## RBAC philosophy - a concrete example

Say you have a junior support engineer "Nika" who should handle DHCP and NAT
for Client A only.

```yaml
# In NetFleet UI: Settings -> Roles -> New Role
role: dhcp-nat-l1
scope:
  type: tenant            # or "site" / "device" / "organization"
  id: client-a
permissions:
  - section: dhcp.lease
    actions: [read, write]
  - section: firewall.nat
    actions: [read, write]
  - section: system.info
    actions: [read]       # so Nika can see which device is which

# In Users -> Nika -> Assign role
user: nika@example.com
role: dhcp-nat-l1
```

Nika now sees only Client A's devices; only DHCP and NAT tabs are visible; and
every action is recorded in the audit log with the request payload. She
literally **cannot** see other clients or other sections - the API rejects with
403 and audits the attempt.

The same policy works the same way whether Client A runs MikroTik or FortiGate;
the driver translates `firewall.nat` to the right vendor-native call.

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend         | **Python 3.12, FastAPI**             | Async, OpenAPI-native, Pydantic v2 |
| Vendor drivers  | **Pluggable Protocol-based**         | Add new vendors without touching API code |
| Authorization   | **Direct Python enforcer**           | Policy is plain SQL rows you can inspect and `git diff`; no DSL to debug |
| DB              | **PostgreSQL 16**                    | RBAC ergonomics, JSONB audit, row-level scoping |
| Cache / pub-sub | **Redis 7**                          | Status cache and worker dispatch |
| Frontend        | **Next.js 15, Tailwind, shadcn/ui**  | Polished, accessible, fast |
| Reverse proxy   | **Caddy 2**                          | Auto HTTPS, zero config |
| Deploy          | **Docker Compose**                   | One-command self-host |
| CI/CD           | **GitHub Actions -> ghcr.io**        | Free public images |

## Roadmap

Shipped:

- Phase 1 - Skeleton (Docker, FastAPI, Next.js, DB)
- Phase 2 - Auth: local + TOTP + Entra OIDC + refresh-token rotation
- Phase 3 - Sites and devices CRUD, encrypted creds, connection test
- Phase 4 - RBAC engine + roles UI + audit log
- Phase 5 - MikroTik driver: IP services, system users, bulk ops
- Phase 6 - VPN (L2TP / PPTP / SSTP / OVPN / IPSec / WireGuard) with reveal-audit,
  firewall filter CRUD + log viewer, queues + quota, routes / ARP / bridge,
  interfaces + VLANs, NTP client + server + clock, SNMP
- Phase 7 - Scheduled daily backups (SFTP) with retention and on-demand restore;
  firmware check
- Phase 8 - Reports (CSV); firmware upgrade trigger + auto-upgrade scheduling
- Phase 10 - Tenant hierarchy (multi-client MSP layer)
- Phase 11 - In-app self-update with pre-update `pg_dump`; observability
  (request-id middleware, global 500 handler)
- CDP / LLDP / MNDP neighbour discovery

Up next:

- Phase 12 - **Linux servers, agentless** (cloud VPS fleets): SSH driver, systemd /
  packages / storage / journald, fleet-wide command runner, nftables with rollback
  guard, `/etc` backups - full plan in [docs/LINUX-PLAN.md](docs/LINUX-PLAN.md)
- Phase 9 - i18n (ka/ru/en) + email notifications (failed backups, leaked
  secrets unrotated past N days, firmware updates available)
- FortiGate driver (FortiOS REST)
- Cisco IOS-XE driver
- Ubiquiti / Aruba drivers
- Open issues: <https://github.com/ITConnectGE/netfleet/issues>

## Contributing

We welcome contributions - bug reports, PRs, docs, translations, **new vendor drivers**.

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md). All contributors agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

Apache License 2.0 - see [LICENSE](LICENSE). Patent grant included; safe for
commercial and MSP-internal use.

## By ITConnect

NetFleet is built and maintained by **[ITConnect](https://itconnect.ge)**, a
Georgian IT outsourcing company. We built it because we needed it ourselves -
and we believe the MSP community deserves an open, modern, vendor-agnostic
alternative to expensive proprietary tools.

If NetFleet saves you time, star the repo,
[tell us](https://github.com/ITConnectGE/netfleet/discussions), or contribute back.

---

<sub>MikroTik and RouterOS are registered trademarks of MikroTikls SIA.
FortiGate is a registered trademark of Fortinet, Inc. Cisco is a registered
trademark of Cisco Systems, Inc. NetFleet is an independent, community-driven
project and is not affiliated with or endorsed by any of these companies.
Vendor names are used solely for descriptive interoperability purposes.</sub>
