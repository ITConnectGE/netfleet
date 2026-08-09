"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import {
  confirmGuard,
  createUfwRule,
  deleteUfwRule,
  disableUfwRule,
  editUfwRule,
  enableUfwRule,
  getEnablePreflight,
  getUfwStatus,
  listPendingGuards,
  moveUfwRule,
  rollbackGuard,
  setUfwEnabled,
  type ChangeGuard,
  type UfwDisabledRule,
  type UfwEnablePreflight,
  type UfwRule,
  type UfwRuleCreate,
  type UfwStatus,
} from "@/lib/ufw";
import { cn } from "@/lib/utils";

/**
 * UFW on a Linux host.
 *
 * The screen's overriding job is to never misrepresent what is being
 * enforced. A firewall that is configured but switched off looks different
 * from one with no rules, and different again from a host with no ufw at all.
 * Rules NetFleet is holding off the host get their own section saying exactly
 * that, because they are genuinely absent from `ufw status` there.
 */
export function UfwFirewall({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<UfwRule | null>(null);
  const [showEnable, setShowEnable] = useState(false);

  const { data, isLoading, error, refetch, isFetching } = useQuery<UfwStatus>({
    queryKey: ["ufw", deviceId],
    queryFn: () => getUfwStatus(deviceId),
    enabled: Boolean(deviceId),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["ufw", deviceId] });
    qc.invalidateQueries({ queryKey: ["ufw-guards", deviceId] });
  };

  const remove = useMutation({
    mutationFn: (v: { spec: string; force: boolean }) =>
      deleteUfwRule(deviceId, v.spec, v.force),
    onSuccess: () => {
      invalidate();
      toast.success("Rule deleted", "Verified — the host is still reachable.");
    },
    onError: (e: Error) => {
      invalidate();
      toast.error("Could not delete the rule", e.message);
    },
  });

  const move = useMutation({
    mutationFn: (v: { spec: string; position: number }) =>
      moveUfwRule(deviceId, v.spec, v.position),
    onSuccess: () => invalidate(),
    onError: (e: Error) => {
      invalidate();
      toast.error("Could not move the rule", e.message);
    },
  });

  const toggle = useMutation({
    mutationFn: (v: { spec: string } | { id: string }) =>
      "spec" in v
        ? disableUfwRule(deviceId, v.spec)
        : enableUfwRule(deviceId, v.id),
    onSuccess: (r, v) => {
      invalidate();
      toast.success(
        "spec" in v ? "Rule disabled" : "Rule enabled",
        // The command carries a note when a re-enabled rule could not land at
        // its old position, which matters because ufw is first-match.
        r.command,
      );
    },
    onError: (e: Error) => {
      invalidate();
      toast.error("Could not change the rule", e.message);
    },
  });

  const disableFirewall = useMutation({
    mutationFn: () => setUfwEnabled(deviceId, { enabled: false }),
    onSuccess: (r) => {
      invalidate();
      toast.success("Firewall turned off", r.command);
    },
    onError: (e: Error) => {
      invalidate();
      toast.error("Could not turn the firewall off", e.message);
    },
  });

  const { data: guards } = useQuery<ChangeGuard[]>({
    queryKey: ["ufw-guards", deviceId],
    queryFn: () => listPendingGuards(deviceId),
    enabled: Boolean(deviceId),
    // A pending guard is on a countdown that ends by itself, so this view has
    // to keep up with a host that is about to change under it.
    refetchInterval: (q) => (q.state.data?.length ? 10_000 : false),
  });

  return (
    <section className="space-y-4">
      {guards?.map((g) => (
        <PendingGuard key={g.id} guard={g} deviceId={deviceId} />
      ))}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Firewall (ufw)</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The host&apos;s own firewall, read and edited live over SSH. Every
            change arms a rollback on the host first, so a rule that cuts
            NetFleet off is undone automatically.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            {isFetching ? "Reading…" : "Reload"}
          </button>
          {data?.installed && !data.active && (
            <button
              type="button"
              onClick={() => setShowEnable(true)}
              className="rounded-md border border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-900 hover:bg-amber-100"
            >
              Turn firewall on
            </button>
          )}
          {data?.installed && data.active && (
            <button
              type="button"
              onClick={() => {
                if (
                  !confirm(
                    "Turn the firewall off?\n\nThis host will accept all inbound traffic, and will stay unprotected across a reboot until it is switched back on.",
                  )
                )
                  return;
                disableFirewall.mutate();
              }}
              disabled={disableFirewall.isPending}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
            >
              Turn firewall off
            </button>
          )}
          {data?.installed && (
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setShowForm((v) => !v);
              }}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              {showForm && !editing ? "Cancel" : "Add rule"}
            </button>
          )}
        </div>
      </div>

      {showEnable && (
        <EnableDialog deviceId={deviceId} onClose={() => setShowEnable(false)} />
      )}

      {(showForm || editing) && data?.installed && (
        <RuleForm
          // Remounts when the edited rule changes, so the form fields reset
          // to the new rule instead of keeping the previous one's values.
          key={editing?.spec ?? "new"}
          deviceId={deviceId}
          editing={editing}
          onDone={() => {
            setShowForm(false);
            setEditing(null);
            invalidate();
          }}
        />
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Reading…</p>}
      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </p>
      )}

      {data && !data.installed && (
        <Notice tone="neutral" title="ufw is not installed on this host">
          Something else may still be filtering traffic — nftables, firewalld or
          raw iptables. NetFleet does not read those yet, so treat this as
          &ldquo;unknown&rdquo;, not as &ldquo;no firewall&rdquo;.
        </Notice>
      )}

      {data?.installed && !data.active && (
        <Notice tone="warn" title="ufw is installed but switched off">
          Nothing below is being enforced. The rules are what ufw would apply if
          it were enabled.
        </Notice>
      )}

      {data?.installed && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat
              label="Status"
              value={data.active ? "Active" : "Inactive"}
              tone={data.active ? "ok" : "warn"}
            />
            <Stat
              label="Incoming"
              value={data.default_incoming ?? "—"}
              tone={data.default_incoming === "allow" ? "warn" : undefined}
            />
            <Stat label="Outgoing" value={data.default_outgoing ?? "—"} />
            <Stat label="Logging" value={data.logging ?? "—"} />
          </div>

          {data.rules.length === 0 ? (
            <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
              No rules are configured.
              {data.default_incoming === "deny" && data.active
                ? " With the default incoming policy set to deny, this host accepts no new inbound connections at all."
                : ""}
            </p>
          ) : (
            <RuleTable
              rules={data.rules}
              numbered={!data.rules_from_added}
              busy={remove.isPending || move.isPending || toggle.isPending}
              onEdit={(r) => {
                setShowForm(false);
                setEditing(r);
              }}
              onDisable={(r) => {
                if (!r.spec) return;
                toggle.mutate({ spec: r.spec });
              }}
              onMove={(r, delta) => {
                if (!r.spec || r.position === null) return;
                move.mutate({ spec: r.spec, position: r.position + delta });
              }}
              onDelete={(r) => {
                if (!r.spec) return;
                if (
                  !confirm(
                    `Delete this rule?\n\n  ${r.spec}\n\nNetFleet will verify the host is still reachable afterwards and undo the change if it is not.`,
                  )
                )
                  return;
                remove.mutate({ spec: r.spec, force: false });
              }}
            />
          )}

          {data.disabled_rules.length > 0 && (
            <DisabledRules
              rules={data.disabled_rules}
              busy={toggle.isPending}
              onEnable={(r) => toggle.mutate({ id: r.id })}
            />
          )}

          {data.rules_from_added && data.rules.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Positions are not shown because ufw only numbers rules while it is
              running. These are the rules as configured.
            </p>
          )}

          {data.app_profiles.length > 0 && (
            <details className="rounded-lg border border-border bg-card p-3 text-sm">
              <summary className="cursor-pointer font-medium">
                Application profiles ({data.app_profiles.length})
              </summary>
              <p className="mt-2 text-xs text-muted-foreground">
                Named port sets ufw knows about on this host. A rule may refer
                to one of these instead of a port number.
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {data.app_profiles.map((p) => (
                  <span
                    key={p}
                    className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}

/**
 * Adding a rule.
 *
 * Simple mode covers what almost every rule actually is — open or close a
 * port — and hides the from/to/interface machinery behind a toggle rather
 * than presenting eight fields to someone who wants to allow 443.
 */
function RuleForm({
  deviceId,
  editing,
  onDone,
}: {
  deviceId: string;
  editing?: UfwRule | null;
  onDone: () => void;
}) {
  const toast = useToast();
  const initial = splitDestination(editing?.destination);
  const [advanced, setAdvanced] = useState(Boolean(editing));
  const [action, setAction] = useState<UfwRuleCreate["action"]>(
    (editing?.action as UfwRuleCreate["action"]) ?? "allow",
  );
  const [direction, setDirection] = useState<UfwRuleCreate["direction"]>(
    (editing?.direction as UfwRuleCreate["direction"]) ?? "in",
  );
  const [port, setPort] = useState(initial.port);
  const [protocol, setProtocol] = useState<"" | "tcp" | "udp">(initial.protocol);
  const [fromAddress, setFromAddress] = useState(
    anywhereToBlank(editing?.source),
  );
  const [toAddress, setToAddress] = useState("");
  const [iface, setIface] = useState(editing?.interface ?? "");
  const [comment, setComment] = useState(editing?.comment ?? "");
  const [position, setPosition] = useState(
    editing?.position ? String(editing.position) : "",
  );

  const body = (): UfwRuleCreate => ({
    action,
    direction,
    port: port.trim() || null,
    protocol: protocol || null,
    from_address: fromAddress.trim() || null,
    to_address: toAddress.trim() || null,
    interface: iface.trim() || null,
    comment: comment.trim() || null,
    position: position.trim() ? Number(position) : null,
  });

  const add = useMutation({
    mutationFn: () =>
      editing?.spec
        ? editUfwRule(deviceId, editing.spec, body())
        : createUfwRule(deviceId, body()),
    onSuccess: (r) => {
      toast.success(editing ? "Rule updated" : "Rule added", r.command);
      onDone();
    },
    onError: (e: Error) =>
      toast.error(
        editing ? "Could not edit the rule" : "Could not add the rule",
        e.message,
      ),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
      className="space-y-3 rounded-lg border border-border bg-card p-3"
    >
      {editing && (
        <p className="text-xs text-muted-foreground">
          Editing <span className="font-mono">{editing.spec}</span>. The
          replacement is added before the original is removed, so the rule is
          never briefly absent.
        </p>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Action">
          <select
            value={action}
            onChange={(e) =>
              setAction(e.target.value as UfwRuleCreate["action"])
            }
            className={INPUT}
          >
            <option value="allow">allow</option>
            <option value="deny">deny</option>
            <option value="reject">reject</option>
            <option value="limit">limit</option>
          </select>
        </Field>
        <Field label="Port(s)" hint="22 · 80,443 · 1024:65535">
          <input
            value={port}
            onChange={(e) => setPort(e.target.value)}
            placeholder="22"
            className={INPUT}
          />
        </Field>
        <Field label="Protocol">
          <select
            value={protocol}
            onChange={(e) => setProtocol(e.target.value as "" | "tcp" | "udp")}
            className={INPUT}
          >
            <option value="tcp">tcp</option>
            <option value="udp">udp</option>
            <option value="">any</option>
          </select>
        </Field>
        <Field label="Comment">
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="why this rule exists"
            className={cn(INPUT, "w-56")}
          />
        </Field>
      </div>

      <button
        type="button"
        onClick={() => setAdvanced((v) => !v)}
        className="text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
      >
        {advanced ? "Hide" : "Show"} source, destination and interface
      </button>

      {advanced && (
        <div className="flex flex-wrap items-end gap-3 border-t border-border pt-3">
          <Field label="Direction">
            <select
              value={direction}
              onChange={(e) =>
                setDirection(e.target.value as UfwRuleCreate["direction"])
              }
              className={INPUT}
            >
              <option value="in">in</option>
              <option value="out">out</option>
              <option value="fwd">forwarded</option>
            </select>
          </Field>
          <Field label="From" hint="IP or CIDR — blank means anywhere">
            <input
              value={fromAddress}
              onChange={(e) => setFromAddress(e.target.value)}
              placeholder="10.0.0.0/8"
              className={INPUT}
            />
          </Field>
          <Field label="To" hint="IP or CIDR — blank means anywhere">
            <input
              value={toAddress}
              onChange={(e) => setToAddress(e.target.value)}
              placeholder="any"
              className={INPUT}
            />
          </Field>
          <Field label="Interface">
            <input
              value={iface}
              onChange={(e) => setIface(e.target.value)}
              placeholder="eth0"
              className={INPUT}
            />
          </Field>
          <Field label="Position" hint="blank appends — ufw is first-match">
            <input
              value={position}
              onChange={(e) => setPosition(e.target.value)}
              placeholder="1"
              inputMode="numeric"
              className={cn(INPUT, "w-20")}
            />
          </Field>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={add.isPending}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {add.isPending
            ? "Applying and verifying…"
            : editing
              ? "Save rule"
              : "Add rule"}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
        >
          Cancel
        </button>
        <p className="text-xs text-muted-foreground">
          The host arms a rollback before the change and NetFleet reconnects to
          check it worked. If the rule cuts NetFleet off, it is undone.
        </p>
      </div>
    </form>
  );
}

/** "22/tcp" -> port 22, protocol tcp. "Anywhere" -> neither. */
function splitDestination(destination?: string): {
  port: string;
  protocol: "" | "tcp" | "udp";
} {
  const value = (destination ?? "").trim();
  if (!value || value.toLowerCase() === "anywhere") {
    return { port: "", protocol: "" };
  }
  const [port, proto] = value.split("/");
  return {
    port: port ?? "",
    protocol: proto === "tcp" || proto === "udp" ? proto : "",
  };
}

function anywhereToBlank(source?: string): string {
  const value = (source ?? "").trim();
  return !value || value.toLowerCase() === "anywhere" ? "" : value;
}

const INPUT =
  "rounded-md border border-input bg-background px-2 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      {children}
      {hint && <span className="text-[10px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

/**
 * An unresolved firewall change, counting down.
 *
 * The host is holding a restore timer. Doing nothing is a valid choice and is
 * stated as such — the countdown reverts the change on its own — so the two
 * buttons are "keep it" and "undo it now", not "OK" and "Cancel".
 */
function PendingGuard({
  guard,
  deviceId,
}: {
  guard: ChangeGuard;
  deviceId: string;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [left, setLeft] = useState(() => secondsLeft(guard.expires_at));

  useEffect(() => {
    const t = setInterval(() => setLeft(secondsLeft(guard.expires_at)), 1000);
    return () => clearInterval(t);
  }, [guard.expires_at]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["ufw", deviceId] });
    qc.invalidateQueries({ queryKey: ["ufw-guards", deviceId] });
  };

  const keep = useMutation({
    mutationFn: () => confirmGuard(deviceId, guard.id),
    onSuccess: () => {
      invalidate();
      toast.success("Change kept", "The rollback timer was cancelled.");
    },
    onError: (e: Error) => toast.error("Could not confirm the change", e.message),
  });

  const undo = useMutation({
    mutationFn: () => rollbackGuard(deviceId, guard.id),
    onSuccess: () => {
      invalidate();
      toast.success("Change undone", "The previous ruleset was restored.");
    },
    onError: (e: Error) => toast.error("Could not roll back", e.message),
  });

  const busy = keep.isPending || undo.isPending;

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50/70 p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-medium text-amber-900">
            Unconfirmed firewall change
            <span className="ml-2 font-mono text-xs font-normal">
              {guard.kind}
            </span>
          </p>
          <p className="mt-0.5 text-xs text-amber-900/90">
            {left > 0 ? (
              <>
                This host will restore its previous firewall configuration by
                itself in <strong>{formatLeft(left)}</strong> unless the change
                is confirmed. NetFleet could not verify the host was still
                reachable after the change.
              </>
            ) : (
              <>
                The window has passed — the host should have restored its
                previous configuration already. Reload to see its current state.
              </>
            )}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => undo.mutate()}
            disabled={busy}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            Undo now
          </button>
          <button
            type="button"
            onClick={() => keep.mutate()}
            disabled={busy}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            Keep the change
          </button>
        </div>
      </div>
    </div>
  );
}

function secondsLeft(iso: string): number {
  return Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 1000));
}

function formatLeft(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function RuleTable({
  rules,
  numbered,
  busy,
  onEdit,
  onMove,
  onDisable,
  onDelete,
}: {
  rules: UfwRule[];
  numbered: boolean;
  busy: boolean;
  onEdit: (rule: UfwRule) => void;
  onMove: (rule: UfwRule, delta: number) => void;
  onDisable: (rule: UfwRule) => void;
  onDelete: (rule: UfwRule) => void;
}) {
  // Order is behaviour, not presentation: ufw stops at the first rule that
  // matches. Only rules ufw itself numbered can be reordered.
  const ordered = rules.filter((r) => r.position !== null);
  const firstPos = ordered.length ? ordered[0].position : null;
  const lastPos = ordered.length ? ordered[ordered.length - 1].position : null;

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full text-sm">
        <thead className="border-b border-border bg-muted/60 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
          <tr>
            {numbered && <th className="w-12 px-3 py-2 font-medium">#</th>}
            <th className="px-3 py-2 font-medium">To</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">From</th>
            <th className="px-3 py-2 font-medium">Interface</th>
            <th className="px-3 py-2 font-medium">Comment</th>
            <th className="w-56 px-3 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {rules.map((r, i) => (
            <tr
              key={`${r.position ?? "x"}-${r.destination}-${r.source}-${i}`}
              className="hover:bg-accent/30"
            >
              {numbered && (
                <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">
                  {r.position ?? r.position_v6 ?? "—"}
                </td>
              )}
              <td className="px-3 py-1.5 font-mono text-xs">
                {r.destination}
                <IpVersionBadge version={r.ip_version} />
              </td>
              <td className="px-3 py-1.5">
                <ActionPill action={r.action} direction={r.direction} />
              </td>
              <td className="px-3 py-1.5 font-mono text-xs">{r.source}</td>
              <td className="px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                {r.interface ?? "—"}
              </td>
              <td className="px-3 py-1.5 text-[11px] text-muted-foreground">
                {r.comment ?? "—"}
              </td>
              <td className="px-3 py-1.5">
                <div className="flex items-center justify-end gap-1">
                  <RowButton
                    label="↑"
                    title="Move up — ufw stops at the first matching rule"
                    onClick={() => onMove(r, -1)}
                    disabled={
                      busy ||
                      !r.spec ||
                      r.position === null ||
                      r.position === firstPos
                    }
                  />
                  <RowButton
                    label="↓"
                    title="Move down — ufw stops at the first matching rule"
                    onClick={() => onMove(r, 1)}
                    disabled={
                      busy ||
                      !r.spec ||
                      r.position === null ||
                      r.position === lastPos
                    }
                  />
                  <RowButton
                    label="Edit"
                    title={r.spec ? `Edit: ${r.spec}` : NO_SPEC}
                    onClick={() => onEdit(r)}
                    disabled={busy || !r.spec}
                  />
                  <RowButton
                    label="Disable"
                    title={
                      r.spec
                        ? "Remove from the host and keep it here — it will not appear in `ufw status` while disabled"
                        : NO_SPEC
                    }
                    onClick={() => onDisable(r)}
                    disabled={busy || !r.spec}
                  />
                  <RowButton
                    label="Delete"
                    danger
                    // Without a spec there is no stable handle for this rule,
                    // and acting by position would hit whichever rule happens
                    // to sit there now.
                    title={r.spec ? `Delete: ${r.spec}` : NO_SPEC}
                    onClick={() => onDelete(r)}
                    disabled={busy || !r.spec}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Rules NetFleet is holding off the host.
 *
 * The disclaimer is a full sentence in the section header, not a tooltip.
 * These rules are genuinely absent from the host: someone who SSHes in and
 * runs `ufw status` will not see them, and this screen must not leave them
 * thinking otherwise.
 */
function DisabledRules({
  rules,
  busy,
  onEnable,
}: {
  rules: UfwDisabledRule[];
  busy: boolean;
  onEnable: (rule: UfwDisabledRule) => void;
}) {
  return (
    <section className="rounded-lg border border-dashed border-border bg-muted/30">
      <div className="border-b border-border/70 px-3 py-2">
        <h3 className="text-sm font-semibold">
          Disabled rules ({rules.length})
        </h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          ufw has no disabled state, so these are removed from the host and
          held here. They are <strong>not</strong> in{" "}
          <span className="font-mono">ufw status</span> on the server — only
          NetFleet knows about them. Enabling one puts it back at the position
          it held, if that position still exists.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border/70 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-12 px-3 py-2 font-medium">Was #</th>
              <th className="px-3 py-2 font-medium">To</th>
              <th className="px-3 py-2 font-medium">Action</th>
              <th className="px-3 py-2 font-medium">From</th>
              <th className="px-3 py-2 font-medium">Comment</th>
              <th className="w-24 px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border/70">
            {rules.map((r) => (
              <tr key={r.id} className="opacity-70 hover:opacity-100">
                <td className="px-3 py-1.5 font-mono text-xs text-muted-foreground">
                  {r.position ?? "—"}
                </td>
                <td className="px-3 py-1.5 font-mono text-xs">
                  {r.destination}
                </td>
                <td className="px-3 py-1.5">
                  <ActionPill action={r.action} direction={r.direction} />
                </td>
                <td className="px-3 py-1.5 font-mono text-xs">{r.source}</td>
                <td className="px-3 py-1.5 text-[11px] text-muted-foreground">
                  {r.comment ?? "—"}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <RowButton
                    label="Enable"
                    title={`Reinstall: ${r.spec}`}
                    onClick={() => onEnable(r)}
                    disabled={busy}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/**
 * The enable dialog.
 *
 * Two states, never one generic warning — the whole reason the pre-flight
 * endpoint exists. When the host is already covered it names the rule doing
 * the covering; when it is not, the fix is the primary button, pre-filled with
 * the address the host actually sees NetFleet arriving from.
 *
 * Proceeding anyway stays available, because an operator at a console may know
 * something NetFleet cannot see. It is a secondary action behind an explicit
 * acknowledgement, and it is audited separately.
 */
function EnableDialog({
  deviceId,
  onClose,
}: {
  deviceId: string;
  onClose: () => void;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [acknowledged, setAcknowledged] = useState(false);

  const { data: pre, isLoading } = useQuery<UfwEnablePreflight>({
    queryKey: ["ufw-preflight", deviceId],
    queryFn: () => getEnablePreflight(deviceId),
  });

  const enable = useMutation({
    mutationFn: (v: { allowManagement: boolean; force: boolean }) =>
      setUfwEnabled(deviceId, {
        enabled: true,
        allowManagement: v.allowManagement,
        force: v.force,
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["ufw", deviceId] });
      qc.invalidateQueries({ queryKey: ["ufw-guards", deviceId] });
      toast.success("Firewall enabled", r.command);
      onClose();
    },
    onError: (e: Error) => {
      qc.invalidateQueries({ queryKey: ["ufw", deviceId] });
      toast.error("Could not enable the firewall", e.message);
    },
  });

  const port = pre?.management_port;
  const address = pre?.management_address;
  const canPrefill = Boolean(pre?.suggested_rule);

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50/70 p-3 text-sm">
      <p className="font-medium text-amber-900">Turn the firewall on?</p>

      {isLoading && (
        <p className="mt-1 text-xs text-amber-900/80">
          Checking how this host sees NetFleet…
        </p>
      )}

      {pre && (
        <>
          {/* Deliberately not "you will lose your connection" — that is false,
              and a dialog people learn is wrong gets dismissed as noise. The
              session that runs the command survives; ufw accepts
              ESTABLISHED,RELATED first. What breaks is the next one. */}
          {pre.covered ? (
            <p className="mt-1 text-xs text-amber-900/90">
              This looks safe. Rule{" "}
              <span className="font-mono">{pre.covering_rule_summary}</span>{" "}
              already permits the connection NetFleet manages this host over (
              {address} → port {port}), so it will still be reachable once the
              firewall is enforcing.
            </p>
          ) : canPrefill ? (
            <p className="mt-1 text-xs text-amber-900/90">
              <strong>Nothing in the ruleset permits NetFleet</strong> ({address}{" "}
              → port {port}), and the default incoming policy is{" "}
              <span className="font-mono">{pre.default_incoming ?? "deny"}</span>
              . Your current session will survive — ufw keeps established
              connections — but NetFleet would not be able to reconnect
              afterwards, and the failure would only show up on the next
              operation.
            </p>
          ) : (
            <p className="mt-1 text-xs text-amber-900/90">
              NetFleet could not determine which address this host sees it
              arriving from, so it cannot pre-fill a rule to keep the path open
              or tell you whether one already exists. Check the ruleset yourself
              before enabling.
            </p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              Cancel
            </button>

            {pre.covered ? (
              <button
                type="button"
                onClick={() =>
                  enable.mutate({ allowManagement: false, force: false })
                }
                disabled={enable.isPending}
                className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {enable.isPending ? "Enabling…" : "Enable firewall"}
              </button>
            ) : (
              <>
                {canPrefill && (
                  <button
                    type="button"
                    onClick={() =>
                      enable.mutate({ allowManagement: true, force: false })
                    }
                    disabled={enable.isPending}
                    className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                  >
                    {enable.isPending
                      ? "Applying…"
                      : `Allow ${port}/tcp from ${address}, then enable`}
                  </button>
                )}
                <label className="flex items-center gap-1.5 text-xs text-amber-900/90">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={(e) => setAcknowledged(e.target.checked)}
                    className="size-3.5 rounded"
                  />
                  I have another way into this host
                </label>
                <button
                  type="button"
                  onClick={() =>
                    enable.mutate({ allowManagement: false, force: true })
                  }
                  disabled={!acknowledged || enable.isPending}
                  className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-40"
                >
                  Enable without the rule
                </button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

const NO_SPEC =
  "NetFleet could not match this rule to a ufw specification, so it cannot " +
  "change it safely";

function RowButton({
  label,
  title,
  onClick,
  disabled,
  danger,
}: {
  label: string;
  title: string;
  onClick: () => void;
  disabled: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "rounded border border-input px-2 py-0.5 text-[11px] font-medium disabled:opacity-40",
        danger ? "hover:bg-destructive/10 hover:text-destructive" : "hover:bg-accent",
      )}
    >
      {label}
    </button>
  );
}

/**
 * ufw installs a v4 and a v6 entry for the same rule and numbers them
 * separately. They are folded into one row here, so the badge is what tells an
 * operator whether IPv6 is actually covered.
 */
function IpVersionBadge({ version }: { version: UfwRule["ip_version"] }) {
  if (version === "both") return null;
  return (
    <span
      className={cn(
        "ml-2 rounded px-1.5 py-0.5 text-[10px] font-medium",
        version === "v6"
          ? "bg-violet-100 text-violet-900"
          : "bg-slate-100 text-slate-700",
      )}
      title={
        version === "v4"
          ? "IPv4 only — IPv6 traffic is not matched by this rule"
          : "IPv6 only — IPv4 traffic is not matched by this rule"
      }
    >
      {version}
    </span>
  );
}

function ActionPill({
  action,
  direction,
}: {
  action: string;
  direction: string;
}) {
  const tone =
    action === "allow"
      ? "bg-emerald-100 text-emerald-900"
      : action === "limit"
        ? "bg-amber-100 text-amber-900"
        : "bg-rose-100 text-rose-900";
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 font-mono text-[11px] font-medium",
        tone,
      )}
    >
      {action.toUpperCase()} {direction.toUpperCase()}
    </span>
  );
}

function Notice({
  tone,
  title,
  children,
}: {
  tone: "warn" | "neutral";
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3 text-sm",
        tone === "warn"
          ? "border-amber-300 bg-amber-50/60 text-amber-900"
          : "border-border bg-muted/40 text-muted-foreground",
      )}
    >
      <p className="font-medium">{title}</p>
      <p className="mt-0.5 text-xs opacity-90">{children}</p>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn";
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 text-sm font-semibold capitalize",
          tone === "warn" && "text-amber-700",
          tone === "ok" && "text-emerald-700",
        )}
      >
        {value}
      </p>
    </div>
  );
}
