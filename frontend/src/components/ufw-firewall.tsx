"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useToast } from "@/components/toast";
import {
  confirmGuard,
  createUfwRule,
  deleteUfwRule,
  getUfwStatus,
  listPendingGuards,
  rollbackGuard,
  type ChangeGuard,
  type UfwRule,
  type UfwRuleCreate,
  type UfwStatus,
} from "@/lib/ufw";
import { cn } from "@/lib/utils";

/**
 * UFW on a Linux host.
 *
 * Read-only for now — stage F1 of docs/UFW-SSH-PLAN.md. The screen's one job
 * at this stage is to never misrepresent enforcement: a firewall that is
 * configured but switched off has to look different from one with no rules,
 * and different again from a host with no ufw at all.
 */
export function UfwFirewall({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [showForm, setShowForm] = useState(false);

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
          {data?.installed && (
            <button
              type="button"
              onClick={() => setShowForm((v) => !v)}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              {showForm ? "Cancel" : "Add rule"}
            </button>
          )}
        </div>
      </div>

      {showForm && data?.installed && (
        <AddRuleForm
          deviceId={deviceId}
          onDone={() => {
            setShowForm(false);
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
              busy={remove.isPending}
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
function AddRuleForm({
  deviceId,
  onDone,
}: {
  deviceId: string;
  onDone: () => void;
}) {
  const toast = useToast();
  const [advanced, setAdvanced] = useState(false);
  const [action, setAction] = useState<UfwRuleCreate["action"]>("allow");
  const [direction, setDirection] = useState<UfwRuleCreate["direction"]>("in");
  const [port, setPort] = useState("");
  const [protocol, setProtocol] = useState<"" | "tcp" | "udp">("tcp");
  const [fromAddress, setFromAddress] = useState("");
  const [toAddress, setToAddress] = useState("");
  const [iface, setIface] = useState("");
  const [comment, setComment] = useState("");
  const [position, setPosition] = useState("");

  const add = useMutation({
    mutationFn: () =>
      createUfwRule(deviceId, {
        action,
        direction,
        port: port.trim() || null,
        protocol: protocol || null,
        from_address: fromAddress.trim() || null,
        to_address: toAddress.trim() || null,
        interface: iface.trim() || null,
        comment: comment.trim() || null,
        position: position.trim() ? Number(position) : null,
      }),
    onSuccess: (r) => {
      toast.success("Rule added", r.command);
      onDone();
    },
    onError: (e: Error) => toast.error("Could not add the rule", e.message),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
      className="space-y-3 rounded-lg border border-border bg-card p-3"
    >
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
          {add.isPending ? "Applying and verifying…" : "Add rule"}
        </button>
        <p className="text-xs text-muted-foreground">
          The host arms a rollback before the change and NetFleet reconnects to
          check it worked. If the rule cuts NetFleet off, it is undone.
        </p>
      </div>
    </form>
  );
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
  onDelete,
}: {
  rules: UfwRule[];
  numbered: boolean;
  busy: boolean;
  onDelete: (rule: UfwRule) => void;
}) {
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
            <th className="w-20 px-3 py-2" />
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
              <td className="px-3 py-1.5 text-right">
                <button
                  type="button"
                  onClick={() => onDelete(r)}
                  // Without a spec there is no stable handle for this rule,
                  // and deleting by position would remove whichever rule
                  // happens to sit there now.
                  disabled={busy || !r.spec}
                  title={
                    r.spec
                      ? `Delete: ${r.spec}`
                      : "NetFleet could not match this rule to a ufw specification, so it cannot delete it safely"
                  }
                  className="rounded border border-input px-2 py-0.5 text-[11px] font-medium hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
