# NetFleet — Linux server management (agentless)

Plan for managing Linux hosts alongside network devices. This is Phase 12 in
[ROADMAP.md](ROADMAP.md); this file is the detailed breakdown.

Scope covers both **public cloud VPSes** and **hosts on internal client networks**.
An internal host needs no public IP and no inbound port-forward — NetFleet connects
outbound over whatever path already reaches it (management VLAN, or the WireGuard
tunnel NetFleet configured on that site's router).

**Approach: agentless.** Every operation is an SSH command executed on demand.
No daemon is installed on managed hosts. This fits the existing architecture
with no structural changes — see "Why this fits" below. An agent-based mode
(push metrics, reach NAT'd hosts) is explicitly out of scope; if it is ever
needed it becomes a separate phase, not a rework of this one.

---

## Why this fits the current design

| Existing piece | What it gives us |
|---|---|
| `drivers/registry.py:8` | vendor → driver map. Adding Linux = one dict entry. |
| `drivers/base.py:17` `Capability` | UI hides sections the driver lacks, so Linux pages appear automatically and RouterOS-only pages stay hidden. |
| `models/device.py:30` `DeviceTransport.SSH` | Already reserved ("future — for vendors without an API"). No enum migration. |
| `models/device.py:62` `ssh_port` | Already a separate column, defaults to 22. |
| `drivers/mikrotik.py:1663` | Established `paramiko` + `asyncio.to_thread` pattern for blocking SSH inside async handlers. |
| `services/bulk.py` | Parallel fan-out across devices already built — reused verbatim for Linux. |
| `device_backups`, `audit_logs`, `device_log_events`, RBAC, scheduler | All vendor-agnostic. Linux inherits them. |

The API layer never imports a concrete driver (it resolves via
`get_driver(device.vendor)`), so most endpoint plumbing is unchanged.

---

## Security invariants

A security review of L1–L3 found three real defects. All are fixed; these are
the invariants that keep them fixed. Breaking any one of them re-opens a path
to root on a managed host.

1. **Every value substituted into a generated script is quoted at the point of
   substitution.** `generate_linux_script` applies `shlex.quote` to all six
   tokens, and `_LINUX_SCRIPT_BODY` deliberately omits the surrounding quotes
   so there is exactly one place where quoting happens. RouterOS is not POSIX
   shell — it gets `_routeros_quote`, not `shlex.quote`.
2. **Quoting is not enough on its own.** A newline inside an already-quoted
   value does not break out of the string, but it *does* survive into
   `authorized_keys` as a second, attacker-chosen key. So: the SSH key comment
   is derived from `device.id` (a UUID) and never from `device.name`;
   `ssh_keys._check_comment` rejects anything outside `[A-Za-z0-9@._-]`; the
   schema rejects control characters in `name` / `host` / `username`; and the
   script caps the key write at `head -n 1`. Each of those alone is
   insufficient — keep all four.
3. **Comment lines are interpolation sites too.** A newline ends the `#` and
   turns the rest into code, so header values go through `_comment_safe`.
4. **Credentials never enter the audit payload.** `_CREDENTIAL_FIELDS` in
   `api/v1/devices.py` excludes them before the write, and `audit._redact`
   matches secret-ish key names by *substring*, so a newly added
   `*_password` / `*_private_key` / `*_token` field is redacted by default
   rather than by someone remembering. Add new credential fields to both.
5. **Host keys fail closed.** `_to_driver_creds` refuses to build credentials
   for an SSH device with no pinned fingerprint; only `test_connection` passes
   `allow_first_connect=True`. Without this the TOFU window never closes for a
   device nobody explicitly tests, because no other code path records the
   fingerprint.
6. **The egress-IP setting is parsed as IP/CIDR**, both when saved
   (`schemas/settings.py`) and when rendered into a script
   (`_validated_mgmt_ips`) — it ends up in a firewall rule inside a root
   script, so an arbitrary string is not acceptable there.

---

## Cross-cutting decisions (defaults chosen; change before L1 starts)

1. **Host keys — TOFU, failing closed.** The first successful *Test connection*
   pins the fingerprint into `devices.ssh_host_key_fingerprint`. Until then no
   other endpoint will talk to the device (409, "run Test connection first"); a
   changed fingerprint afterwards fails the connection and requires an explicit
   re-pin. `AutoAddPolicy` (used for RouterOS backups today) is *not* acceptable
   here.
2. **Privilege — unprivileged user + sudo.** Root login is supported but not
   the documented path. `become_method = sudo`, password supplied via stdin to
   `sudo -n -S`. Passwordless sudo (NOPASSWD) is the recommended setup.
3. **Distro targets for MVP — Debian/Ubuntu and RHEL/Rocky/Alma.** Detected
   from `/etc/os-release`. Alpine/SUSE degrade gracefully: `system_info` works,
   package/service ops report "unsupported os_family" rather than guessing.
4. **Route naming collision.** `/dashboard/devices/[id]/services` already exists
   and means RouterOS IP services. Linux systemd units go to
   `/dashboard/devices/[id]/systemd`. Do not overload the existing route.
5. **Metrics stay in Zabbix.** NetFleet shows *current* state and performs
   *actions*. It does not build a historical time-series store for managed
   hosts. `host_metric_samples` remains the NetFleet host's own stats only.

---

## Stage L1 — Schema + credentials foundation (M) — **done**

The only migration in the whole plan that touches the existing `devices` table.

- [x] Migration `0022_linux_hosts`, adding to `devices`:
  - `device_class` enum (`network` | `server`), NOT NULL, default `network`, indexed
  - `os_family` (`debian` | `rhel` | `alpine` | `suse` | `unknown`), nullable
  - `os_version` `String(64)`, nullable — populated on connect like `firmware`
  - `ssh_private_key_encrypted` `Text`, nullable
  - `ssh_key_passphrase_encrypted` `String(1024)`, nullable
  - `become_method` (`none` | `sudo`), NOT NULL, default `none`
  - `become_password_encrypted` `String(1024)`, nullable
  - `ssh_host_key_fingerprint` `String(128)`, nullable
- [x] `models/device.py` — the columns above + `DeviceClass`, `OsFamily`,
      `BecomeMethod` StrEnums; exported from `models/__init__.py`
- [x] `drivers/base.py` `DeviceCredentials` gains `ssh_port`,
      `ssh_private_key`, `ssh_key_passphrase`, `become_method`,
      `become_password`, `host_key_fingerprint`. All defaulted so the MikroTik
      driver is untouched.
- [x] `services/device.py` `_to_driver_creds` — decrypts the new fields and
      carries `ssh_port` on the credentials rather than as a per-call kwarg
- [x] `schemas/device.py` validation: `vendor == "linux"` ⇒ `transport` must be
      `ssh`, no `api_key`, and exactly one of (password, private key,
      generate-key) must be present; `port` is kept in step with `ssh_port`
- [x] Device **create** UI: vendor-conditional fields (auth mode, sudo toggle,
      port/username defaults switch with the vendor)
- [x] Schema hardening: control characters rejected in `name` / `host` /
      `username`; POSIX account-name rule on server usernames (enforced in the
      service layer for PATCH, which carries no vendor field)
- [ ] Device **edit** UI: rotate SSH key, change sudo mode, clear the pinned
      host key. `reset_host_key` already exists on `DeviceUpdate`, and it is
      now the only recovery path after a legitimate host rebuild — so this is
      no longer merely cosmetic.
- [ ] Tests — the repo has no pytest suite yet, so L1 is covered by a
      scratchpad harness rather than committed tests. Worth fixing before L5
      starts writing to hosts.

### L1b — Onboarding, same flow as RouterOS — **done**

- [x] `services/ssh_keys.py` — Ed25519 keypair generation, public-half
      derivation, OpenSSH-style `SHA256:` fingerprints
- [x] Key generated server-side on device create; only the private half is
      stored (Fernet), the public half is rendered into the script on demand
- [x] `services/device_onboarding.py` `generate_linux_script` — creates the
      management user (key-only, password login locked), installs the public
      key, writes `/etc/sudoers.d/90-netfleet` with `visudo` validation, opens
      the SSH port for NetFleet's egress IPs, prints host key fingerprints
- [x] Firewall detection: ufw → firewalld → nftables → iptables, first match
      wins; never enables an inactive firewall and never edits
      `AllowUsers`/`AllowGroups`, because both lock the operator out
- [x] Idempotent: re-running replaces NetFleet's own key and rules rather than
      stacking duplicates
- [x] `GET /devices/{id}/onboarding-script` dispatches on `device_class` and
      returns `.sh` or `.rsc`

**Ships:** create a Linux device, download the script, run it on the host.

---

## Stage L2 — SSH transport layer (M) — **done**

Isolated from the driver so it can be tested and reused.

- [x] `drivers/ssh_transport.py`
  - `run(creds, argv, *, become, stdin, timeout, max_output)` → `CommandResult`
  - `run_many(creds, [Command, …])` — **one connection per batch**, because a
    call like `system_info` is nine tiny reads and paying TCP + auth nine times
    is what would make the page feel slow
  - blocking paramiko inside `asyncio.to_thread`, mirroring `mikrotik.py:1663`
  - **argv list only** — never a formatted shell string; joined through
    `shlex.join` at the boundary
  - `sudo -n --` on the NOPASSWD path, `sudo -S -p ''` with the password on
    stdin otherwise; asking to escalate on a `become_method=none` device raises
    a typed error instead of hanging on a prompt nobody can answer
  - stdout and stderr drained together via `select` — reading stdout to
    completion first deadlocks the moment a command writes more to stderr than
    the channel window holds
  - output hard-capped (1 MB default) so a runaway `cat /dev/urandom` cannot
    exhaust API memory
  - host-key pinning: mismatch raises `HostKeyMismatch`, first connect returns
    the observed fingerprint for the caller to store
  - `look_for_keys=False`, `allow_agent=False` — the API host's own `~/.ssh`
    must never influence which key is presented
- [x] `services/device.py` test-connection persists the fingerprint, `os_family`
      and `os_version` on first successful connect
- [ ] Tests: rc propagation, timeout, truncation, sudo failure, host-key
      mismatch (blocked on the repo having no test suite)

**Ships:** internal capability, exercised through the driver above it.

---

## Stage L3 — LinuxDriver, read-only core (L) — **mostly done**

- [x] `drivers/linux.py` — `vendor = "linux"`, `display_name = "Linux (SSH)"`
- [x] `/etc/os-release` detection → `os_family` via `ID`, falling back to
      `ID_LIKE` so an unheard-of derivative still resolves to its ancestor
- [x] Per-family differences kept to a lookup table inside the driver, not
      separate driver classes
- [x] Implemented Protocol methods, all read-only:
  - `test_connection`
  - `system_info` — hostname, kernel, distro, uptime + load from `/proc`,
    memory from `/proc/meminfo`, model/serial from `/sys/class/dmi` when
    readable (silently null when not). Load average is normalised by core
    count into a percentage so it means the same thing as the RouterOS
    driver's CPU figure. Memory uses `MemAvailable`, not `MemFree` —
    counting page cache as "used" makes every healthy box look full.
  - `interfaces_list`, `ip_addresses_list`, `ip_routes_list`, `ip_arp_list` —
    all from `ip -j link|addr|route|neigh` (native JSON, no text scraping).
    IPv6 route listing is best-effort: a host with IPv6 off must not take the
    v4 table down with it.
  - `tool_ping`, `tool_traceroute`
- [x] Capabilities declared: `SYSTEM_INFO`, `SYSTEM_REBOOT`, `INTERFACE_LIST`,
      `IP_ADDRESS`, `IP_ROUTE`, `IP_NEIGHBOR`, `TOOL_PING`, `TOOL_TRACEROUTE`
- [x] Registered in `drivers/registry.py`
- [x] Fleet list + device detail: vendor / distro icons, distro + version in the
      "Model / OS" column, kernel in "Firmware / Kernel", SSH port instead of the
      RouterOS API port
- [x] Capability-gated tabs — the device tab strip and the System sub-tabs are
      both filtered by the driver's capability set, so a Linux host no longer
      offers DHCP, Queues or a RouterOS log viewer
- [x] `UnsupportedOperation` → HTTP 501. A missing driver method used to surface
      as `AttributeError: 'LinuxDriver' object has no attribute 'log_list'`
- [ ] Poller (`workers/poller.py`) — expected to need no change, not yet verified
      against a live host

### L3b — Clock, NTP, resources, storage — **done**

- [x] `system.clock` capability; `clock_get` / `clock_set` via `timedatectl`,
      `ntp_client_get` / `ntp_client_set`. Reads cover systemd-timesyncd and
      chrony; **writes cover timesyncd only** (Ubuntu/Debian default) and refuse
      clearly on a chrony host rather than silently doing nothing.
- [x] Setting the wall clock by hand is refused while NTP is on, with the reason,
      instead of passing through a raw `timedatectl` error
- [x] `disk.usage` capability + `GET /devices/{id}/disks`; `df -PT -B1` plus
      `df -Pi`, pseudo-filesystems filtered out, inodes reported alongside bytes
- [x] `GET /devices/{id}/resources` — `system_info` was never exposed by any
      endpoint, so live CPU/RAM was unreachable from the UI. Now carries
      absolute figures too: core count, 1/5/15 load, memory and swap totals.
- [x] UI: Resources card (CPU / memory / swap / uptime) on the overview for
      servers in place of the RouterOS firmware card, and a Storage tab

**Ships:** add a Linux host, see it online, view system info, interfaces,
addresses, routes, ARP. RouterOS-only pages stay hidden by capability gating.

---

## Why one `linux` driver and not one per distribution

`vendor` selects **how to talk to a device**, not what it runs. Ubuntu, Debian,
Rocky and Alpine all speak plain SSH — the transport, onboarding, host-key
pinning and capability plumbing are byte-for-byte identical. What actually
differs is a short list of commands: the package manager, a few unit names,
the firewall front-end. Those branch on `os_family`, detected from
`/etc/os-release` on connect.

Splitting into `ubuntu`, `centos`, … would:

- duplicate the entire transport and onboarding layer per distro, so every
  fix (the paramiko 4 `DSSKey` removal, say) needs applying N times;
- require the operator to declare the distro in advance and be right — pick
  "Ubuntu" for a Rocky box and every command fails, where detection simply
  reads the truth;
- break on re-provisioning: a host rebuilt from CentOS to Rocky would need
  the device deleted and recreated rather than just reconnecting.

Development order is Ubuntu/Debian first — that is what the deployment
actually runs. RHEL-family paths land as the command table grows, and
anything not yet covered fails with a clear "this host uses X, which NetFleet
cannot edit yet" rather than guessing.

---

## Stage L4 — Linux-specific read capabilities (L)

- [ ] `Capability` additions: `svc.systemd`, `pkg.manager`, `disk.usage`,
      `proc.list`, `log.journal`
- [ ] `drivers/base.py` dataclasses: `SystemdUnit`, `PackageUpdate`,
      `DiskUsage`, `ProcessInfo`, `JournalEntry`
- [ ] Protocol + driver methods:
  - `services_list` — `systemctl list-units --type=service -o json`
  - `packages_list_upgradable` — `apt list --upgradable` / `dnf check-update`,
    plus security-only count and `reboot_required` flag
  - `disk_usage` — `df -PT` + inode usage; SMART deferred
  - `processes_top` — top N by CPU and by RSS from `ps`
  - `journal_tail` — `journalctl -o json -n N` with unit/priority/since filters
- [ ] `api/v1/linux.py`, mounted at `/devices` in `api/v1/__init__.py`
- [ ] `frontend/src/lib/linux.ts`
- [ ] Pages under `/dashboard/devices/[id]/`: `systemd`, `packages`, `storage`,
      `processes`, `journal`
- [ ] RBAC sections registered: `linux.service`, `linux.package`,
      `linux.storage`, `linux.process`, `linux.journal` (read only so far)

**Ships:** a genuinely useful read-only server dashboard.

---

## Stage L5 — Write ops: services, packages, host users (M)

- [ ] `service_start` / `stop` / `restart` / `enable` / `disable`, each returning
      the post-action unit state so the UI can confirm rather than assume
- [ ] `package_upgrade_all` and `package_upgrade(names)`; long-running, so run
      through the existing job/events pipeline rather than a blocking request
- [ ] `device_users_list` / `device_user_set_password` / `set_disabled` via
      `getent passwd`, `chpasswd`, `usermod -L/-U`; `authorized_keys` add/remove
- [ ] Reuse the firmware surface for packages: nightly job in
      `workers/scheduler.py` fills `firmware_available` with the update count;
      `auto_upgrade_enabled` + window columns already exist and apply as-is
- [ ] Every write goes through the existing audit + events path
- [ ] Guard: refuse to stop/disable `sshd` (and the unit currently carrying the
      session) — that is a self-inflicted outage with no recovery path

**Ships:** day-to-day server operations from the UI.

---

## Stage L6 — Command runner + bulk execution (M)

The highest-value feature of the whole phase.

- [ ] `POST /devices/{id}/exec`
  - **Catalog mode** — a curated list of named, parameterless commands
    (`disk usage`, `who`, `failed units`, `last 100 auth failures`). Gated by
    `linux.command:read`.
  - **Free-form mode** — arbitrary argv. Gated by a separate
    `linux.command:execute` permission that no default role holds.
- [ ] `services/bulk.py` gains `bulk_linux_exec`, reusing the existing
      parallel fan-out and `BulkOperationResult` shape
- [ ] `/dashboard/bulk` gets a "Run command" tab: host selector, command,
      per-host output with rc, collapsible
- [ ] Full command text + truncated output written to the audit log on every run

**Ships:** "run this across 40 servers and show me the output."

---

## Stage L7 — Backups (M)

- [ ] `system_backup` — tar.gz of a configurable path list (default `/etc`),
      plus a package manifest (`dpkg --get-selections` / `rpm -qa`) and the
      `ip`/`systemctl` state dumps, streamed back over SFTP
- [ ] Reuses `device_backups` + the retention policy from Phase 7a as-is
- [ ] Restore is **download only** in this stage. No automated restore-to-host.

**Ships:** Linux hosts appear in the same backup history and retention as routers.

---

## Stage L8 — Firewall + WireGuard (L)

Last because it is the only place where a mistake severs your own access.

- [ ] **Lockout guard, built first and non-optional.** Before any ruleset write:
      snapshot the current ruleset, schedule
      `systemd-run --on-active=120 nft -f <snapshot>`, apply the change, then
      require an explicit `POST .../confirm` within the window to cancel the
      timer. Same contract as RouterOS safe-mode. No write path may bypass it.
- [ ] nftables primary: `nft -j list ruleset` read, rule add/delete/move mapped
      onto the existing `FilterRule` / `NatRule` dataclasses
- [ ] iptables / ufw / firewalld: **read-only** rendering, with a clear "managed
      by X, edit not supported" banner. Do not attempt to write through wrappers.
- [ ] WireGuard: `wg show` + wg-quick config rendering →
      `wireguard_interfaces_list`, `wireguard_peers_list`, peer add/remove
- [ ] `services/wg_s2s.py` accepts a Linux host as a tunnel endpoint, making
      Linux↔MikroTik site-to-site possible from the existing UI

**Ships:** Linux firewall visibility, safe editing, and Linux as a WireGuard peer.

---

## Stage L9 — Web terminal (M, optional)

- [ ] WebSocket endpoint proxying an interactive SSH channel
- [ ] xterm.js in the frontend
- [ ] Session recording written to audit storage; gated by its own permission
- [ ] Only after L1–L8 are stable — it is a convenience, not a capability

---

## Explicit non-goals

- Agent / daemon on managed hosts
- Desired-state configuration management (Ansible-style convergence)
- Windows server management
- Historical metric storage for managed hosts (Zabbix owns this)
- Automated restore of a Linux backup onto a host

---

## Sizing legend

S = ~2 files, ~30 min build · M = ~5 files, ~1 h · L = ~10 files, ~2-3 h
