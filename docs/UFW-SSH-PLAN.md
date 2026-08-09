# NetFleet — UFW firewall + SSH key management

Detailed breakdown of the first half of **Stage L8** in
[LINUX-PLAN.md](LINUX-PLAN.md), plus the two SSH-key items left open in L1 and
L5. Scope is Ubuntu/Debian hosts running `ufw`.

Two independent tracks:

| Track | What | Stages | Depends on |
|---|---|---|---|
| **F** | UFW: view, enable/disable, rule add/edit/delete/enable/disable | F1 → F6 | F2 gates every write |
| **S** | SSH keys: management-key rotation, per-user `authorized_keys` | S1, S2 | nothing — can run in parallel |

Each stage below is independently shippable, independently revertible, and has
its own acceptance check. Nothing in track F after F1 lands before F2 does.

---

## Amendment to L8: ufw becomes writable

`LINUX-PLAN.md:411` currently reads *"iptables / ufw / firewalld: read-only
rendering… Do not attempt to write through wrappers."* That decision is
reversed here for ufw specifically, and the reasoning matters because it does
**not** generalise to the others.

On an Ubuntu host with ufw active, ufw is not a wrapper sitting beside the
ruleset — it **owns** it. It persists rules in `/etc/ufw/user.rules` and
regenerates the live nftables ruleset from those files on every `ufw reload`,
on `ufw enable`, and at boot. Writing nftables directly underneath an active
ufw is therefore the unsafe option: the change works, survives testing, and
then silently vanishes the next time anything touches ufw. Going through the
`ufw` CLI is the only way to make a change that persists on such a host.

What stays unchanged from the original decision:

- **firewalld and raw iptables remain read-only.** Same reasoning inverted —
  there we have no single owning front-end we can drive safely.
- **A host is edited through exactly one front-end.** If ufw is present and
  active, NetFleet drives ufw and will not write nftables on that host, ever.
  `_detect_firewall` already establishes the precedence order
  (`device_onboarding.py:144`); it becomes the authority for which write path
  is permitted, not just which one to render.

---

## The failure mode this plan is built around

Worth stating precisely, because the obvious mental model is wrong and it
changes the design.

`ufw enable` with the default `deny (incoming)` policy **does not** kill the
SSH session that ran it. ufw's input chain accepts `ESTABLISHED,RELATED`
before it evaluates anything else, so the connection that made the change
survives, reports success, and looks completely healthy.

The **next** connection is the one that fails. NetFleet opens a fresh SSH
connection per operation (`ssh_transport.run_many` connects, runs the batch,
closes), so the sequence is: change applied → success reported → host
unreachable from that moment on, with no error anywhere near the action that
caused it.

Two consequences shape the whole design:

1. **Success of the command proves nothing.** Every write must be validated by
   a *second, brand-new* connection, not by the exit status of the command.
2. **There is no still-open session to undo it with.** `ssh_transport` closes
   the client after every batch (`ssh_transport.py:311`), so by the time the
   verification fails, the connection that made the change is already gone.
   Recovery therefore cannot depend on NetFleet reaching the host at all —
   which is precisely why the dead-man timer has to live on the host.

So the guard has two layers, and F2 builds both. The timer is the guarantee;
the probe is what turns "wait two minutes and hope" into an immediate answer
whenever the host is still reachable.

---

## Stage F1 — UFW read-only (M) — **done**

Read-only, so it can land ahead of the guard and give something visible
immediately.

- [x] `Capability.FIREWALL_UFW = "firewall.ufw"` in `drivers/base.py`, added to
      `LinuxDriver.capabilities` and to `DRIVER_SECTIONS` in `services/rbac.py`
      (`read` / `write` / `execute` — `execute` is enable/disable of the
      firewall itself, a bigger hammer than editing a rule and worth granting
      separately)
- [x] Dataclasses in `drivers/base.py`: `UfwStatus` (installed, active, logging
      level, default incoming/outgoing/routed policy, rules, app profiles) and
      `UfwRule`. Field names follow ufw's own columns — `destination` is its
      "To", `source` its "From".
- [x] `drivers/linux.py`:
  - `ufw_status()` — one batch: `ufw version`, `ufw status numbered verbose`,
    `ufw show added`, `ufw app list`. All escalated: `ufw status` answers an
    unprivileged user with "ERROR: You need to be root", which would otherwise
    read as an empty ruleset.
  - **`ufw show added` is read even when ufw is inactive**, because
    `ufw status` prints `Status: inactive` and *no rules at all*. Without it a
    disabled firewall looks like an empty one, which is the single most
    dangerous thing this screen could get wrong.
  - ufw-not-installed is a distinct, typed outcome — not an empty list
- [x] Parser handling the real output shapes: port ranges, `80,443/tcp` lists,
      `ALLOW IN` / `DENY IN` / `REJECT IN` / `LIMIT IN` / `ALLOW FWD`,
      `on <iface>`, `Anywhere (v6)`, app profiles, `# comment`. Splits on the
      action keyword rather than by column offset — both the To and From
      columns can contain spaces, and offset slicing loses the interface.
- [x] **v4/v6 pairing.** One `ufw allow 22/tcp` produces two numbered entries.
      The parser pairs them into one logical rule carrying `v4`/`v6`/`both`,
      because rendering them as two rows makes every ruleset look duplicated
      and invites the operator to delete "the extra one".
- [x] `spec` from `ufw show added` attached to each rule as the stable handle
      for F3's delete — but **only when the two listings have equal counts**. A
      v6-only rule can desynchronise them, and pinning the wrong spec to a rule
      would mean a later delete removes the wrong one.
- [x] `schemas/ufw.py`, `services/ufw.py`, `api/v1/ufw.py` mounted at `/devices`
- [x] `GET /devices/{id}/firewall/ufw`
- [x] `frontend/src/lib/ufw.ts`; the existing firewall tab branches on
      `device_class === "server"` into a new `components/ufw-firewall.tsx`
- [x] Banner when `Status: inactive`: rules exist but nothing is enforced. A
      third state for "ufw not installed", worded as *unknown* rather than *no
      firewall* — nftables or firewalld may still be filtering.
- [x] Tests: `backend/tests/test_ufw_parsers.py` (21), plus a `UfwRule` pair in
      `test_api_serialisation.py`

**Ships:** every Ubuntu host's firewall is visible in NetFleet.
**Accept:** open the tab on an active host and an inactive host; both show the
correct rules and the correct enforcement state.
**Status: done** — pending the acceptance check against a live host.

---

## Stage F2 — The lockout guard (L) — **done**

Built once, used by every stage below. This is the stage to not rush.

- [x] **Layer 1 — host-side dead-man timer.** Before any write:
  1. snapshot `/etc/ufw/user.rules`, `user6.rules`, `ufw.conf` into
     `/var/tmp/netfleet-guard-<token>`, one `cp` per file — a single `cp` with
     three sources fails for *all* of them on a host with IPv6 off, silently
     producing a snapshot that restores nothing
  2. write a POSIX-`sh` restore script beside them (not bash: a minimal image
     may have none, and a restore script that cannot run looks like a guard)
  3. `systemd-run --on-active=120 --unit=netfleet-guard-<token>` it
  4. apply the change
  5. on confirmation, `systemctl stop netfleet-guard-<token>.timer` — the
     **timer**, not the service; stopping only the service leaves the timer to
     fire later and revert a change already confirmed

  The restore script re-reads `ENABLED=` from the restored `ufw.conf` and runs
  `ufw --force enable|disable` accordingly, so one script covers a rule change
  and an enable/disable equally. It resolves `ufw` via `command -v` with a
  `/usr/sbin/ufw` fallback, because systemd-run's environment is not a login
  shell.

  The timer lives on the host on purpose: it still fires when the thing that
  broke is the path between NetFleet and the host — including when the API
  process itself dies mid-operation.

- [x] **Layer 2 — fresh-connection probe.** Immediately after applying, open a
      *new* SSH connection and run `true`. On success, cancel the timer and
      report the change as verified — turning the common case from "wait 120s
      and hope" into a sub-second answer. On failure, attempt an explicit
      restore over another new connection; if that fails too, leave the timer
      armed and tell the operator exactly when the host will restore itself.
      The probe never *replaces* the timer, because a probe failure is by
      definition the case where we can no longer reach the host.
- [x] **Arm before apply.** The whole snapshot/script/`systemd-run` sequence is
      one batch that runs before the change and touches no ufw state itself. A
      connection that dies mid-batch must never leave the change applied with
      no timer behind it.
- [x] `services/change_guard.py`, with `run_guarded(session, …, apply=…)` as
      the single entry point. Write paths hand it a callable; they do not get
      to assemble the steps themselves. It **refuses outright** on a host with
      no `systemd-run` (`GuardUnavailable`) rather than proceeding unguarded —
      an unguarded write that looks guarded is worse than one honestly refused.
- [x] The guard row is committed **before** the change is applied, so a process
      that dies between the two still has a record naming the armed timer.
- [x] Model + migration `0025_change_guards`: device, token, kind, armed_at,
      expires_at, state (`armed` / `confirmed` / `rolled_back` / `expired`),
      so the UI can show "unconfirmed change, 86s left"
- [x] `GET /devices/{id}/firewall/guards`,
      `POST /devices/{id}/firewall/guards/{guard_id}/confirm` and `.../rollback`
- [x] Startup reconciliation in `main.py` (`expire_stale_guards`), mirroring
      `packages.mark_orphaned_runs`: guards whose window elapsed are marked
      `expired`, because the host restored itself and what NetFleet lost was
      only the chance to watch it happen
- [x] UI: a countdown banner on the firewall tab with **"Keep the change"** and
      **"Undo now"**. Doing nothing is a valid choice and says so — the host
      reverts on its own.
- [x] **Management-path detection**, shared by F3 and F6. The address to protect
      is read from `$SSH_CONNECTION` on the live session — `<client_ip>
      <client_port> <server_ip> <server_port>` — which is the address our packets
      actually arrive from *after* any NAT, and the port sshd is actually
      listening on.

      Deliberately **not** `organization.netfleet_external_ips`. Internal hosts
      are reached over a management VLAN or the WireGuard tunnel
      (`LINUX-PLAN.md:6`), and such a host never sees NetFleet's external
      address. Whitelisting the configured egress IP there would cause exactly
      the lockout it is meant to prevent. Configured egress IPs may be offered
      as *additional* entries; they are never the primary source.

      `device.ssh_port` is likewise a fallback only — the observed server port
      wins, because the stored value can be stale.
- [x] The guard token is `uuid4().hex`, validated as lowercase hex before it is
      interpolated anywhere — it names both a systemd unit and a directory that
      `rm -rf` later runs against
- [x] Tests: `backend/tests/test_change_guard.py` (16) — arm ordering, per-file
      snapshot, timer-not-service cancellation, loud failure when the timer
      cannot be scheduled, restore-script shape, token validation,
      management-path parsing

**Ships:** no user-visible change beyond the pending-change banner. This is the
stage that makes the rest safe.
**Accept:** deliberately apply a rule that blocks the management port on a test
host and confirm NetFleet reverts it automatically and says so.
**Status: machinery done, acceptance deferred to F3.** The guard has no caller
until the first write exists, so the live check — break the management path,
watch the host restore itself — runs as part of F3's acceptance. Everything
testable without a write is covered by unit tests; the orchestration in
`run_guarded` (probe → confirm / rollback) needs a database and is not yet
covered.

---

## Stage F3 — Rule add + delete (M) — **done**

- [x] `ufw_rule_add(spec, *, position=None)` → `ufw allow|deny|reject|limit …`,
      or `ufw insert <n> …` when a position is given. Always the **extended**
      grammar (`from … to … port … proto …`) even where the short form would
      do, because the short form's meaning depends on argument order.
- [x] `ufw_rule_delete(spec)` — **deleted by rule specification, never by
      number.** ufw renumbers on every delete, so a number captured when the
      page rendered may address a different rule by the time the click lands.
      Deleting by spec also removes the v4 and v6 halves together. `route`
      stays in front of `delete` (`ufw route delete RULE`), the trailing
      `comment` clause is stripped because ufw rejects it on a delete, and
      `--force` is passed so nothing can prompt on a channel nobody can answer.
- [x] Both wrapped in the F2 guard, via `run_guarded`. Neither service function
      touches the driver directly.
- [x] **Management-path protection.** A delete is refused when the rule is the
      only one permitting the live management path detected in F2
      (`$SSH_CONNECTION`, not the configured egress IP). `limit` counts as
      coverage alongside `allow` — it permits the connection and only
      rate-limits new ones. A source that cannot be parsed is *not* claimed as
      coverage: overstating protection is the dangerous direction, because it
      makes a rule look redundant when it is the only one holding the door
      open. Overridable by an explicit `force`, audited distinctly.
- [x] Input validation in two layers: the schema for a readable error, and
      `_assert_safe_ufw_spec` in the driver so nothing malformed reaches the
      CLI regardless of caller. The argv path stops shell injection; this stops
      a rule ufw half-accepts and then enforces as something else. Hostnames
      are refused outright — ufw resolves one at rule-creation time and freezes
      the answer, so the rule silently stops matching when the name moves.
- [x] `POST /devices/{id}/firewall/ufw/rules` and
      `POST .../rules/delete` (POST, not DELETE: the rule is identified by a
      multi-word spec with spaces and quotes, which has no business in a path
      segment). `require_permission("firewall.ufw", "write")`, audited, and a
      reverted change is audited as `failed` with the outcome recorded.
- [x] UI: add form (simple: action + port + protocol + comment; advanced:
      direction, from/to, interface, position), delete with a confirm naming
      the exact spec. Delete is disabled on a rule with no spec, because
      without one there is no stable handle.
- [x] Tests: `backend/tests/test_ufw_rules.py` (24)

**Ships:** open and close ports from NetFleet.
**Accept:** add a rule, see it on the host; delete it, see it gone; try to
delete the SSH rule and get refused with a readable reason. **Also the deferred
F2 acceptance:** add a rule that blocks the management path and confirm the
host restores itself and NetFleet says so.

---

## Stage F4 — Rule edit + reorder (M) — **done**

Sized S in the original plan. It became M because reordering needed a real
first-match simulation, not the rule-counting F3 shipped with — see below.

- [x] **Edit** inserts the replacement, confirms it landed, **then** deletes the
      original. Never the reverse: the overlap window is harmless, the gap
      window is a lockout.
- [x] Edit aborts if ufw *skipped* the insert. ufw refuses a duplicate with
      "Skipping adding existing rule" and **exit status 0**, so the rule count
      before and after is the only honest signal — deleting the original after
      a skipped insert would remove the rule and leave nothing in its place.
- [x] **Move deletes first and re-inserts**, the opposite order, because a move
      produces a rule identical to one already installed and ufw refuses
      duplicates. Both commands share one connection, so the window is a single
      round trip, and the guard's snapshot covers it. This asymmetry is
      deliberate and is the reason edit and move are separate driver methods
      rather than one primitive.
- [x] `route` precedes `insert` (`ufw route insert N RULE`), matching
      `ufw route delete RULE`
- [x] IPv6-only rules refuse to move, with the reason. `ufw insert N` numbers
      the IPv4 list; a v6-only rule's number in the combined table is a
      different one, and using it would reorder some unrelated rule.
- [x] `POST /devices/{id}/firewall/ufw/rules/edit` and `.../rules/move`, both
      identifying the rule by spec rather than by number
- [x] UI: edit reuses the add form pre-filled, arrow buttons per row, both
      disabled on a rule with no spec
- [x] Tests: `backend/tests/test_ufw_order.py` (18)

### The safety check became a simulation

F3 refused a delete by counting how many rules covered the management path.
That reasoning cannot see a reorder at all: moving a `deny` above the `allow`
that keeps NetFleet reachable takes the host away while the count stays
exactly the same.

So the check was rewritten as `ufw_path_verdict` — walk the projected ruleset
in order and return what ufw's first-match evaluation would do to NetFleet's
own connection. Delete, edit and move now each supply a `project` function
returning the ruleset they would leave behind, and share one verdict.
Falling through to a default of `deny` counts as a lockout, because an empty
ruleset on a host with the stock incoming policy is exactly as unreachable as
an explicit deny.

One deliberate escape hatch: if the *current* ruleset already reads as locked
out while we are demonstrably talking to the host, the model is wrong about
that host and is not allowed to block a change on the strength of it. That is
logged, and the host-side guard remains the backstop.

**Ships:** rules can be corrected and reordered without delete-and-retype.
**Accept:** edit a rule's port and confirm both position and comment survive;
move a deny above the SSH allow and confirm NetFleet refuses with the reason.

---

## Stage F5 — Rule enable / disable (M) — **done**

The one place where NetFleet must hold state the host does not.

- [x] Model + migration `0026_ufw_disabled_rules`: device, full rule spec,
      position, disabled_at, disabled_by. Unique on `(device_id, spec)` —
      disabling the same rule twice would leave a duplicate to re-enable.
- [x] Disable = capture spec + position → guarded delete from host → store row.
      **The row is written only after the host confirms the removal.** The
      reverse order would leave NetFleet claiming a rule is disabled while it
      is still being enforced.
- [x] Enable = `ufw insert <stored position>` (clamped to the current rule
      count) → guarded → drop the row
- [x] **Drift handling.** The stored position is a hint, not a promise. The
      driver clamps it — `ufw insert` errors on a position past the end — and
      returns where the rule actually landed; when that differs from the stored
      position the response says so. It matters because ufw is first-match, so
      a rule returning two places lower can mean something different.
- [x] **Re-enabling is safety-checked like a move.** A deny coming back above
      the allow that keeps NetFleet reachable is a lockout, so `enable` runs
      the same first-match projection F4 built. The projection clamps its
      insert index exactly as the driver does, or it would judge a placement
      the host would never produce.
- [x] Display fields are re-parsed from the stored spec rather than stored
      twice, so the disabled table shows the same columns as the live one and
      there is one source of truth.
- [x] **Honesty in the UI, not in a tooltip.** Disabled rules render in a
      visually separate, dashed section whose header states in a full sentence
      that they are removed from the host and invisible in `ufw status` there.
      Anyone reading the host directly must not be misled by our screen.
- [x] Orphan cleanup: rows cascade with the device and the organisation
- [x] Tests: `backend/tests/test_ufw_toggle.py` (12)

**Ships:** the toggle you asked for, without lying about where it lives.
**Accept:** disable a rule, confirm `ufw status` on the host no longer shows it,
re-enable, confirm it returns at the same position. Then delete a rule *above*
a disabled one and re-enable it, to see the drift note.

---

## Stage F6 — Firewall enable / disable (M) — **done**

- [x] `ufw --force disable` — guarded, and the confirm says the host is
      unprotected **and stays unprotected across reboot**
- [x] `ufw --force enable` — `--force` because plain `ufw enable` asks
      *"Command may disrupt existing ssh connections. Proceed with operation
      (y|n)?"* and would hang on a channel nobody can answer
- [x] Both gated on `firewall.ufw:execute` rather than `:write` — a bigger
      hammer than editing a rule, and worth granting separately
- [x] **The default policy is read from `/etc/default/ufw` too.** `ufw status
      verbose` prints the `Default:` line only while ufw is *running*, so
      without this the pre-flight would reason about a disabled firewall with
      no idea what policy switching it on would apply. The file speaks
      iptables targets (`DROP`/`ACCEPT`/`REJECT`) and ufw's output speaks
      `deny`/`allow`/`reject`; translated at the boundary so one vocabulary
      reaches the rest of the system. The running answer always wins where
      both exist.

### The enable dialog

Enable is not refused. It is explained, with the fix pre-filled — an operator
on a console, or one who knows something we do not, is allowed to proceed.

- [x] `GET /devices/{id}/firewall/ufw/enable-preflight` returns what the dialog
      renders: the detected management path (F2), the pending ruleset, and
      whether anything in it already covers that path. Read-only.
- [x] **Two states, never one generic warning.** A dialog that looks identical
      whether or not the host is safe trains people to click through it.
  - **Covered** — names the rule that protects them. Ordinary confirm, primary
    button enables.
  - **Not covered** — states the consequence and offers the fix as the
    **primary, pre-filled** action: *"Allow `<observed_port>/tcp` from
    `<observed_ip>`, then enable"*. Proceeding without it is a secondary
    button, disabled until an *"I have another way into this host"* checkbox is
    ticked, and audited as `enable_forced` so a forced enable is findable in
    the log without reading payloads.
- [x] **The rule goes in before the enable, in one batch.** That ordering is
      the entire value of the offered fix — a rule added afterwards would have
      to arrive over a connection that no longer works. The enable is not
      attempted at all if the rule was rejected, so a bad rule surfaces as
      itself rather than as a mysterious lockout.
- [x] **Accurate wording.** Not "you will lose your connection" — that is false
      and gets the dialog dismissed as noise. The dialog says the current
      session survives because ufw keeps established connections, and that what
      breaks is NetFleet's *next* one, on the next operation.
- [x] Guard window shortened to 60s for this operation — the fresh-connection
      probe is the real test and it either passes in a second or does not; a
      longer window just means a longer outage before the host rescues itself.
      The dialog is prevention, the guard is recovery, neither replaces the
      other.
- [x] Edge case: no management path detectable (`$SSH_CONNECTION` unset) ⇒
      neither the fix nor the safety claim can be made, and the dialog says
      exactly that rather than guessing an address or implying it is safe
- [x] Tests: `backend/tests/test_ufw_enable.py` (9)

**Ships:** full UFW control.
**Accept:** on a host with no SSH rule, open the enable dialog and confirm it
shows the *not covered* state with the observed address pre-filled; take the
offered fix and confirm the host is still reachable afterwards. Repeat on a host
that already has the rule and confirm the dialog names it instead. Then, on a
throwaway host, proceed *without* the fix and confirm the F2 guard reverts it.

---

## Stage S1 — Management SSH key rotation (M) — parallel track

Closes the open L1 item *"Device edit UI: rotate SSH key"*
(`LINUX-PLAN.md:126`).

- [ ] `POST /devices/{id}/rotate-ssh-key`, `require_permission("devices", "write")`
- [ ] Sequence, in this order and no other:
  1. generate a new Ed25519 pair (`services/ssh_keys.generate_ed25519_keypair`)
  2. append the new public half to the management user's `authorized_keys`,
     **alongside** the existing one
  3. open a **new** connection authenticating with the new key only
  4. only on success, store the new private half and remove the old line
  5. on any failure, remove the new line and keep the old key — the device is
     exactly as it was
- [ ] Key comment stays `netfleet-<device.id>`, and the `authorized_keys` write
      keeps all four defences from the security invariants
      (`LINUX-PLAN.md:47`): UUID-derived comment, `_check_comment`, schema
      control-character rejection, single-line cap
- [ ] Audited as a credential operation; the private half never enters the audit
      payload (`_CREDENTIAL_FIELDS`, `audit._redact`)
- [ ] UI: button on the device edit page, with the result stated plainly

**Ships:** rotate a host's management key without touching the host by hand.
**Accept:** rotate, then run Test connection; break it deliberately (wrong
permissions on `.ssh`) and confirm the old key still works afterwards.

---

## Stage S2 — Per-user `authorized_keys` (M) — parallel track

Closes the open L5 item *"`authorized_keys` add/remove"* (`LINUX-PLAN.md:356`).

- [ ] `authorized_keys_list(user)` / `_add` / `_remove`, keyed by fingerprint
      rather than by line number
- [ ] **Permissions are the whole game.** `~/.ssh` at `0700`, `authorized_keys`
      at `0600`, both owned by the target user. Wrong ownership makes sshd
      ignore the key *silently* — no error, no log at default verbosity, just a
      key that does not work. Every write sets them explicitly rather than
      assuming.
- [ ] Optional "generate a new pair": the private half is returned **once** in
      the response and never stored, following the existing secret-reveal audit
      path
- [ ] NetFleet's own `netfleet-<uuid>` key is protected from removal through
      this endpoint — removing it is S1's job, with S1's verification
- [ ] `root` and the management account follow the existing `_is_protected`
      rule (`drivers/linux.py:1430`)
- [ ] UI: expandable per-user key list inside `components/linux-accounts.tsx`,
      next to the password reset that already exists there

**Ships:** manage who can SSH into a host, per account.
**Accept:** add a key for a normal user and log in with it; confirm the key is
ignored-then-working across a deliberate permission mistake and its fix.

---

## Already built — not in scope

Listed so no stage re-does them:

- Unix account list, create, delete, lock/unlock, group membership —
  `components/linux-accounts.tsx`, shipped 0.48.0
- Password reset for a host account — `POST /{device_id}/system-users/{username}/password`
- Bulk password reset across hosts — `api/v1/bulk.py:29`

---

## Sequencing

```
F1 (read) ──► F2 (guard) ──► F3 (add/delete) ──► F4 (edit/reorder) ──► F5 (toggle) ──► F6 (enable/disable)
   done         done            done                done                 done            done
S1 (key rotation) ─────────── independent ───────────►
S2 (authorized_keys) ──────── independent ───────────►
```

Track F shipped across v0.51.0 – v0.54.0. Track S has not started.

**The one thing no test can establish** is the live acceptance: apply a rule
that blocks the management path on a real host and watch it restore itself
inside the window. Every layer below that is covered by unit tests, and the
orchestration in `run_guarded` (probe → confirm / rollback) is still covered
by neither, because it needs a database.

F1 first because it is harmless and visible. F2 next because everything after
it is not. F6 last because it is the only operation that can take a host away
in one click.

Sizing legend as in [LINUX-PLAN.md](LINUX-PLAN.md): S = ~2 files / ~30 min ·
M = ~5 files / ~1 h · L = ~10 files / ~2-3 h.
