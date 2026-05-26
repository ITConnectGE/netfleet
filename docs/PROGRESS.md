# NetFleet â€” Progress Snapshot

Last updated: 2026-05-26

This document captures *what's been built so far*, file-by-file. Pair with
[ROADMAP.md](ROADMAP.md) for what's left.

## Status by phase

| Phase | What | Status |
|-------|------|--------|
| 0 | Architecture & branding | âœ… |
| 1 | Skeleton (Docker, Caddy, FastAPI, Next.js, Updater stub) | âœ… |
| 2 | Auth (Local + TOTP + Entra OIDC + Setup wizard) | âœ… |
| 3 | Sites + Devices + Vendor driver + Test connection | âœ… |
| 4 | RBAC (Roles + Users + Audit) | âœ… |
| 5 | IP services + Device users + Bulk reset | âœ… |
| 6a | Secret reveal foundation + Risk report | âœ… |
| 6bâ€“g | VPN / Firewall filter / Queues / Routes / Interfaces | â³ pending |
| 7 | Scheduled backups + Firmware checks | â³ pending |
| 8 | Firmware upgrades + Reports | â³ pending |
| 9 | i18n + email + webhooks | â³ pending |

## File inventory

### Top-level
- `README.md` â€” marketing + comparison table + roadmap link
- `LICENSE` â€” Apache 2.0
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
- `.gitignore`, `.env.example` (full `NETFLEET_*` catalog)
- `docker-compose.yml` â€” production stack (caddy, postgres, redis, api, worker, web, updater)
- `docker-compose.dev.yml` â€” dev overrides (builds from local source, exposes ports)
- `Caddyfile` â€” auto-HTTPS, security headers, HTTP/3, WebSocket pass-through
- `install.sh` â€” one-command Ubuntu installer
- `docs/architecture.drawio` â€” 6-page architecture diagram
- `docs/installation.md`, `docs/ROADMAP.md`, `docs/PROGRESS.md` (this file)

### Backend (`backend/`)
- `Dockerfile` â€” multi-stage (base/deps/dev/prod), tini, non-root user
- `pyproject.toml` â€” FastAPI, SQLAlchemy[asyncio], asyncpg, librouteros, authlib, argon2-cffi, pyotp, cryptography, jose, redis, structlog, casbin (vestigial; not used â€” see `services/rbac.py`)
- `docker-entrypoint.sh` â€” runs `alembic upgrade head` then starts uvicorn

#### Core
- `app/main.py` â€” FastAPI factory, lifespan (init/close DB), CORS, SessionMiddleware (for Authlib OIDC)
- `app/core/config.py` â€” Pydantic settings with `NETFLEET_*` env prefix
- `app/core/database.py` â€” async engine + session
- `app/core/logging.py` â€” structlog (JSON in prod, console in dev)
- `app/core/security.py` â€” Argon2 password hashing, JWT issue/verify, Fernet field encryption, opaque refresh tokens

#### Models
- `models/mixins.py` â€” `IdMixin` (PgUUID), `TimestampsMixin`, `TableNameMixin`
- `models/organization.py`
- `models/user.py` â€” local + OIDC auth, TOTP, is_admin
- `models/refresh_token.py` â€” with rotation chain (replaced_by_id) + revoked_at
- `models/audit_log.py` â€” JSONB payload, outcome enum
- `models/site.py`
- `models/device.py` â€” vendor + encrypted creds + status + last_seen
- `models/role.py` â€” Role / Permission / RoleAssignment with scope (organization/site/device)
- `models/secret_audit.py` â€” SecretReveal + SecretRotation (the risk report substrate)

#### Migrations
- `0001_initial` â€” organizations, users, refresh_tokens, audit_logs
- `0002_sites_devices` â€” sites + devices + status/transport enums
- `0003_rbac` â€” roles + permissions + role_assignments + permission_action/assignment_scope enums
- `0004_secret_audit` â€” secret_reveals + secret_rotations + secret_kind enum

#### Services
- `services/auth.py` â€” local + TOTP login, refresh rotation with reuse detection, TOTP enrollment
- `services/oidc.py` â€” generic OIDC (Authlib), `upsert_user_from_claims`
- `services/setup.py` â€” first-run wizard (creates org + admin + seeds system roles)
- `services/rbac.py` â€” direct enforcer, section catalog (APP_SECTIONS + DRIVER_SECTIONS), `seed_system_roles`
- `services/site.py`, `services/device.py`, `services/role.py`, `services/user.py` â€” CRUD
- `services/device_ops.py` â€” IP services + device users (single device)
- `services/bulk.py` â€” bulk password reset (parallel)
- `services/audit.py` â€” `write_audit()` with automatic secret redaction
- `services/secret_audit.py` â€” `record_reveal`, `record_rotation`, `user_risk_report`

#### Drivers
- `drivers/base.py` â€” `VendorDriver` Protocol, 30+ `Capability` enum, dataclasses for SystemInfo / DhcpLease / NatRule / IpService / DeviceUser / PppSecret / WireguardInterface / WireguardPeer / BackupArtifact / DeviceCredentials
- `drivers/registry.py` â€” driver registry + `list_vendors`
- `drivers/mikrotik.py` â€” librouteros-based MikroTik driver. Implemented: test_connection, system_info, dhcp_leases, firewall_nat CRUD, ip_services list+set, device_users list+set_password+set_disabled, ppp_secrets full CRUD + reveal, wireguard interfaces+peers CRUD + reveal_keys, system_backup (with file-download stub)

#### API endpoints (`api/v1/`)
- `system.py` â€” `/health`, `/version`
- `setup.py` â€” `/setup/status`, `/setup` (first-run only)
- `auth.py` â€” local login, TOTP verify, refresh, logout, /me, TOTP enrol
- `oidc.py` â€” `/auth/oidc/start`, `/callback`
- `drivers.py` â€” driver catalog
- `sites.py`, `devices.py` â€” CRUD + test-connection
- `device_ops.py` â€” `/devices/{id}/ip-services`, `/devices/{id}/system-users`
- `bulk.py` â€” `/bulk/device-users/password-reset`
- `roles.py` â€” CRUD + section catalog
- `users.py` â€” CRUD + assignments + risk-report
- `audit.py` â€” filterable + paginated query
- `dependencies.py` â€” `get_current_user`, `require_admin`, `require_permission(section, action)` factory

#### Workers
- `app/workers/poller.py` â€” heartbeat stub; Phase 6 will iterate devices

### Frontend (`frontend/`)
- `Dockerfile` â€” multi-stage (deps/dev/build/prod with standalone output), non-root
- `package.json` â€” Next 15, React 19 RC, Tanstack Query, ky, zod, lucide, tailwind, shadcn primitives
- `next.config.mjs`, `tsconfig.json`, `tailwind.config.ts`, `postcss.config.mjs`
- `src/middleware.ts` â€” edge redirect to /setup when system not initialized

#### Lib
- `lib/api.ts` â€” ky client with single-flight refresh on 401
- `lib/auth-storage.ts` â€” in-memory + sessionStorage with subscriber pattern
- `lib/auth.ts`, `lib/sites.ts`, `lib/devices.ts`, `lib/drivers.ts`, `lib/roles.ts`, `lib/users.ts`, `lib/audit.ts`, `lib/device-ops.ts`, `lib/bulk.ts`, `lib/risk-report.ts`

#### Pages
- `app/page.tsx` â€” landing
- `app/login/page.tsx` â€” 2-phase (password â†’ TOTP)
- `app/setup/page.tsx` â€” first-run wizard
- `app/auth/oidc/complete/page.tsx` â€” token-from-hash bouncer
- `app/dashboard/layout.tsx` â€” auth-required layout with top nav
- `app/dashboard/page.tsx` â€” overview with live counts
- `app/dashboard/sites/page.tsx` â€” list + inline create form
- `app/dashboard/devices/page.tsx` â€” list with vendor names + status pills + add form
- `app/dashboard/devices/[id]/layout.tsx` â€” tab nav (Overview / IP services / Device users / VPN / Backups)
- `app/dashboard/devices/[id]/page.tsx` â€” overview + test connection + driver capabilities
- `app/dashboard/devices/[id]/services/page.tsx` â€” IP services with toggle + port edit
- `app/dashboard/devices/[id]/system-users/page.tsx` â€” device users + password reset modal + disable
- `app/dashboard/bulk/page.tsx` â€” bulk password reset across many devices
- `app/dashboard/users/page.tsx` â€” list + create
- `app/dashboard/users/[id]/page.tsx` â€” detail with role assignments + password reset + risk report
- `app/dashboard/roles/page.tsx` â€” list + create with permission matrix editor
- `app/dashboard/audit/page.tsx` â€” paginated + filterable audit log

#### Components
- `components/providers.tsx` â€” React Query Provider
- `components/risk-report-card.tsx` â€” "secrets to rotate before disabling user"

### Updater (`updater/`)
- `Dockerfile`
- `pyproject.toml`
- `main.py` â€” `/status` (polls GitHub Releases), `/update` (stub â€” Phase 7 will flesh out)

### CI/CD (`.github/`)
- `workflows/ci.yml` â€” backend lint + type-check + tests, frontend lint + build, docker smoke build
- `workflows/release.yml` â€” on `v*` tag: build 3 images, push to ghcr.io, create GitHub Release
- `ISSUE_TEMPLATE/bug.yml`, `feature.yml`

## Key design decisions

1. **Direct Python RBAC enforcer** (not Casbin). The `casbin` dep is in pyproject.toml but unused. Decision: simpler debug, no DSL surface. README mentions Casbin â€” update to "direct enforcer" when polishing for v1.

2. **Multi-vendor abstraction first.** Every device-touching call goes through `VendorDriver.{method}`. MikroTik is the only driver today, but the API surface won't change when FortiGate / Cisco ship.

3. **Credentials never round-trip.** UI sends `password` once on create; subsequent API responses only return `has_password: bool`. Reveal goes through a dedicated audited endpoint.

4. **Secret reveal audit is foundational, not optional.** Every code path that exposes plaintext secret material MUST call `record_reveal()`. Phase 6b/6c/6d endpoints WILL be reviewed for this.

5. **`docker.sock` lives only in the `updater` container.** API / web / worker / postgres / redis never see it. Compromise of API does not equal host compromise.

## Things NOT yet exercised

- âš ï¸ Docker stack has never been booted end-to-end. `docker compose up` will fail today because `ghcr.io/itconnectge/netfleet-*` images don't exist yet.
- âš ï¸ Alembic migrations haven't been run against a real Postgres. There may be a small bug in `0003`/`0004` enum ordering, etc.
- âš ï¸ No automated tests yet. CI runs lint + typecheck, but `pytest -q` runs against an empty test suite.
- âš ï¸ Login â†’ Setup â†’ Dashboard end-to-end has not been clicked through.

## Recommended next session

1. Open this in a fresh session, paste the goal: "continue NetFleet from Phase 6b (VPN: L2TP & PPTP) per docs/ROADMAP.md"
2. Verify the stack boots locally first: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`
3. Hit `/setup` in a browser, create the org + admin
4. Once green, proceed to Phase 6b
