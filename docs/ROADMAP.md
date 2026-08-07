# NetFleet — Roadmap

This document is the source of truth for *what's left to build*. It complements
[PROGRESS.md](PROGRESS.md), which is the source of truth for *what's been built*.

Phases are sized so that each one ships a deployable, demoable artefact. Anything
larger than ~10 backend files + ~5 frontend files gets split.

---

## Phase 6 — Device operations (in progress)

The single biggest phase. The MikroTik driver implements most of these calls
already; what's missing is the API + UI layer. Split into deliverable chunks.

### 6a — Secret reveal foundation ✅

- [x] `secret_reveals` + `secret_rotations` models + `0004_secret_audit` migration
- [x] `services/secret_audit.py` — `record_reveal`, `record_rotation`, `user_risk_report`
- [x] `schemas/secret_audit.py`
- [x] `GET /users/{id}/risk-report` endpoint
- [x] `RiskReportCard` component wired into `/dashboard/users/[id]`

### 6b — VPN: L2TP & PPTP

- [ ] `services/vpn.py` — wraps PPP secrets driver methods
- [ ] `api/v1/vpn.py` — endpoints under `/devices/{id}/vpn/ppp-secrets`
  - `GET` list, `POST` create, `PATCH /{sid}/password`, `DELETE /{sid}`
  - `POST /{sid}/reveal` → records reveal + returns plaintext (gated by `secret.reveal:execute`)
- [ ] `/dashboard/devices/[id]/vpn/page.tsx` — tabs for L2TP / PPTP
- [ ] Reveal modal with justification field

### 6c — VPN: WireGuard + config download

- [ ] `api/v1/wireguard.py` under `/devices/{id}/wireguard/{interfaces,peers}`
- [ ] `POST /devices/{id}/wireguard/peers/{pid}/config-download`
  - Takes `WireguardPeerConfigRequest` (server endpoint, client address, DNS, allowed-ips)
  - Calls `driver.wireguard_peer_reveal_keys` → records reveal
  - Generates `.conf` text and returns as `application/octet-stream`
- [ ] WG peer create / delete UI; "Download config" button per peer

### 6d — Firewall filter + RouterOS log viewer

- [ ] Driver: `firewall_filter_*` methods + `log_list` (calls `/log/print`)
- [ ] Endpoints: `/devices/{id}/firewall/filter`, `/devices/{id}/logs`
- [ ] UI tabs: Filter (CRUD with `log` + `log-prefix` columns), Logs (filterable by topic, live tail)

### 6e — Queues / quota

- [ ] Driver: `queue_simple_*`, `queue_tree_*` (already in capability list)
- [ ] Endpoints + UI for bandwidth limits per IP/subnet/interface
- [ ] Quota counters (total bytes) + manual reset

### 6f — Routes / ARP / Bridge hosts

- [ ] Driver: `ip_routes_*` (read+write), `ip_arp_list` (read), `bridge_hosts_list` (read)
- [ ] Endpoints under `/devices/{id}/{routes,arp,bridge-hosts}`
- [ ] UI tabs: Routes (CRUD), ARP (read-only diagnostics), Bridge hosts (read-only)

### 6g — Interfaces + VLANs

- [ ] Driver: `interfaces_list` (with RX/TX stats), `vlan_*`
- [ ] Endpoints + UI tabs

---

## Phase 7 — Scheduled fleet operations

A single new worker (`app/workers/scheduler.py`) drives all daily jobs:

### 7a — Backups

- [ ] `BackupArtifact` storage layer — file written to `/opt/netfleet/data/backups/devices/{device_id}/{YYYY-MM-DD}.{backup,rsc}`
- [ ] Retention policy — configurable, default 30 days
- [ ] `device_backups` history table
- [ ] Per-device "Backup now" + history list + download in `/dashboard/devices/[id]/backups`
- [ ] Dashboard widget: "Last successful fleet backup: <time>"

### 7b — Firmware check (daily scan)

- [ ] Driver: `firmware_check_updates()` → returns `(current, available, channel)`
- [ ] Worker job: iterates enabled devices once per day, writes to `device.firmware_*`
- [ ] Dashboard widget: "X devices have a firmware update available"
- [ ] Per-device badge in devices list when update is available

---

## Phase 8 — Firmware upgrades + Reports

### 8a — Firmware upgrades

- [ ] Driver: `firmware_download`, `firmware_install` (triggers reboot), `routerboard_upgrade`
- [ ] Per-device `auto_upgrade_enabled` + `maintenance_window_cron` columns
- [ ] `POST /devices/{id}/firmware/upgrade` endpoint with `pre_backup: bool`
- [ ] Worker job: every minute, find devices whose maintenance window matches now + need upgrade, run them
- [ ] UI: firmware tab with current/available/upgrade button + auto-upgrade scheduler

### 8b — Reports + CSV export

- [ ] Aggregations over `audit_logs` + `secret_reveals`:
  - **User Activity** — per user, sections touched, devices touched
  - **Device Activity** — per device timeline
  - **Secret Access** — who saw which secrets, rotation status
  - **Change Report** — all writes in date range, grouped by section/user
- [ ] `/dashboard/reports` with date-range picker + filters
- [ ] CSV export per report

---

## Phase 9 — Polish & i18n

- [ ] i18n: Georgian / Russian / English UI strings
- [ ] Email notifications (SMTP already wired in config):
  - User invite emails
  - Backup failure alerts
  - Firmware update available
  - Secret reveal alerts (optional)
- [ ] Webhook integrations (Slack / Teams) for the same events
- [ ] OpenTelemetry tracing (optional)

---

## Phase 12 — Linux servers (agentless)

Bring Linux hosts — bare metal, VMs, and cloud VPSes — into the same fleet as
network devices. Agentless: every operation is an on-demand SSH command, no
daemon installed on managed hosts.

Detailed stage-by-stage breakdown: **[LINUX-PLAN.md](LINUX-PLAN.md)**.

- [x] L1 — Schema + credentials foundation (`device_class`, SSH key, sudo, host-key pin) — M
- [x] L1b — Onboarding: server-side keypair + `sudo bash` script (user, key, sudoers, firewall) — M
- [x] L2 — SSH transport layer (`drivers/ssh_transport.py`) — M
- [x] L3 — `LinuxDriver` read-only core (system info, interfaces, addresses, routes, ARP) — L
- [ ] L4 — Linux read capabilities (systemd, packages, disk, processes, journald) — L
- [ ] L5 — Write ops (service control, package upgrades, host users) — M
- [ ] L6 — Command runner + bulk execution across the fleet — M
- [ ] L7 — Backups (`/etc` archive + package manifest, reuses Phase 7a retention) — M
- [ ] L8 — Firewall with mandatory lockout guard + WireGuard — L
  - [ ] L8a — UFW: view, enable/disable, rule add/edit/delete/toggle — see
        [UFW-SSH-PLAN.md](UFW-SSH-PLAN.md)
  - [ ] L8b — SSH keys: management-key rotation + per-user `authorized_keys` — same doc
  - [ ] L8c — nftables + WireGuard
- [ ] L9 — Web terminal (optional) — M

---

## Future / wishlist

- FortiGate vendor driver (FortiOS REST)
- Cisco IOS-XE driver (RESTCONF)
- Ubiquiti UISP driver
- Multi-tenant SaaS mode (multiple MSPs in one instance with row-level isolation)
- Ansible-compatible export of device configs
- ABAC policies (time-of-day, geo, etc.) — would swap the direct enforcer for Casbin
- Mobile app companion

---

## Sizing legend

S = ~2 files, ~30 min build
M = ~5 files, ~1 h build
L = ~10 files, ~2-3 h build
