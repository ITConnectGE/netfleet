"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useToast } from "@/components/toast";
import {
  createFilterRule,
  deleteFilterRule,
  listFilterRules,
  moveFilterRule,
  setFilterRuleDisabled,
  type FilterRule,
} from "@/lib/firewall";

const CHAINS = ["input", "forward", "output"] as const;
const ACTIONS = [
  "accept",
  "drop",
  "reject",
  "fasttrack-connection",
  "log",
  "passthrough",
] as const;

export default function FirewallPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const qc = useQueryClient();
  const toast = useToast();

  const [chainFilter, setChainFilter] = useState<"all" | "input" | "forward" | "output">("all");
  const [showForm, setShowForm] = useState(false);

  const { data: rules, isLoading, error } = useQuery<FilterRule[]>({
    queryKey: ["fw-filter", deviceId],
    queryFn: () => listFilterRules(deviceId),
  });

  const toggle = useMutation({
    mutationFn: ({ id, disabled }: { id: string; disabled: boolean }) =>
      setFilterRuleDisabled(deviceId, id, disabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fw-filter", deviceId] }),
  });
  const del = useMutation({
    mutationFn: (id: string) => deleteFilterRule(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fw-filter", deviceId] }),
  });
  const move = useMutation({
    mutationFn: ({ id, beforeId }: { id: string; beforeId: string | null }) =>
      moveFilterRule(deviceId, id, beforeId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fw-filter", deviceId] }),
    onError: (e: Error) => toast.error("Move failed", e.message),
  });

  const filtered = (rules ?? []).filter((r) =>
    chainFilter === "all" ? true : r.chain === chainFilter,
  );

  // Reordering happens within a chain: each rule's "previous" and "next"
  // are the nearest same-chain rules in the full list. That keeps the
  // semantics intuitive even when the chain filter is on.
  function neighborsOf(rule: FilterRule) {
    const sameChain = (rules ?? []).filter((r) => r.chain === rule.chain);
    const i = sameChain.findIndex((r) => r.id === rule.id);
    return {
      isFirst: i <= 0,
      isLast: i < 0 || i === sameChain.length - 1,
      prev: i > 0 ? sameChain[i - 1] : null,
      next: i >= 0 && i < sameChain.length - 1 ? sameChain[i + 1] : null,
      afterNext: i >= 0 && i < sameChain.length - 2 ? sameChain[i + 2] : null,
      first: sameChain[0] ?? null,
      last: sameChain[sameChain.length - 1] ?? null,
    };
  }

  function onMoveUp(r: FilterRule) {
    if (!r.id) return;
    const n = neighborsOf(r);
    if (n.isFirst || !n.prev?.id) return;
    move.mutate({ id: r.id, beforeId: n.prev.id });
  }

  function onMoveDown(r: FilterRule) {
    if (!r.id) return;
    const n = neighborsOf(r);
    if (n.isLast) return;
    // "Down by one" = land in front of the rule after the next, i.e.
    // swap with the next. When there's no rule-after-next, the moved
    // rule should land below the current next — same chain or not,
    // RouterOS' move with destination=null pushes it to the global
    // bottom which still works because there's nothing after it in
    // this chain.
    move.mutate({ id: r.id, beforeId: n.afterNext?.id ?? null });
  }

  function onMoveTop(r: FilterRule) {
    if (!r.id) return;
    const n = neighborsOf(r);
    if (n.isFirst || !n.first?.id || n.first.id === r.id) return;
    move.mutate({ id: r.id, beforeId: n.first.id });
  }

  function onMoveBottom(r: FilterRule) {
    if (!r.id) return;
    const n = neighborsOf(r);
    if (n.isLast) return;
    move.mutate({ id: r.id, beforeId: null });
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Firewall — Filter rules</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Tick <strong>log</strong> on a rule to mirror its hits into the device&apos;s log topic — view them on the Logs tab.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New rule"}
        </button>
      </div>

      <div className="mt-4 inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
        {(["all", ...CHAINS] as const).map((c) => (
          <button
            key={c}
            onClick={() => setChainFilter(c)}
            className={`rounded px-3 py-1.5 font-medium transition ${
              chainFilter === c
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {c.toUpperCase()}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      {showForm && (
        <RuleForm
          deviceId={deviceId}
          defaultChain={chainFilter === "all" ? "forward" : chainFilter}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["fw-filter", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-6 overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="w-20 px-3 py-2.5 font-medium">Order</th>
              <th className="px-3 py-2.5 font-medium">Chain</th>
              <th className="px-3 py-2.5 font-medium">Action</th>
              <th className="px-3 py-2.5 font-medium">Src</th>
              <th className="px-3 py-2.5 font-medium">Dst</th>
              <th className="px-3 py-2.5 font-medium">Proto</th>
              <th className="px-3 py-2.5 font-medium">Dst port</th>
              <th className="px-3 py-2.5 font-medium">In iface</th>
              <th className="px-3 py-2.5 font-medium">State</th>
              <th className="px-3 py-2.5 font-medium">Log</th>
              <th className="px-3 py-2.5 font-medium">Comment</th>
              <th className="px-3 py-2.5 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={12} className="px-3 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={12} className="px-3 py-8 text-center text-muted-foreground">
                  No rules.
                </td>
              </tr>
            )}
            {filtered.map((r) => {
              const n = neighborsOf(r);
              return (
                <tr key={r.id} className={`hover:bg-accent/30 ${r.disabled ? "opacity-50" : ""}`}>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-0.5">
                      <OrderButton
                        title="Move to top of chain"
                        disabled={n.isFirst || move.isPending}
                        onClick={() => onMoveTop(r)}
                      >
                        ⏶
                      </OrderButton>
                      <OrderButton
                        title="Move up one"
                        disabled={n.isFirst || move.isPending}
                        onClick={() => onMoveUp(r)}
                      >
                        ▲
                      </OrderButton>
                      <OrderButton
                        title="Move down one"
                        disabled={n.isLast || move.isPending}
                        onClick={() => onMoveDown(r)}
                      >
                        ▼
                      </OrderButton>
                      <OrderButton
                        title="Move to bottom of chain"
                        disabled={n.isLast || move.isPending}
                        onClick={() => onMoveBottom(r)}
                      >
                        ⏷
                      </OrderButton>
                    </div>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{r.chain}</td>
                  <td className="px-3 py-2">
                    <ActionPill action={r.action} />
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px]">
                    {r.src_address ?? r.src_address_list ?? "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px]">
                    {r.dst_address ?? r.dst_address_list ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs">{r.protocol ?? "—"}</td>
                  <td className="px-3 py-2 font-mono text-[11px]">{r.dst_port ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">{r.in_interface ?? "—"}</td>
                  <td className="px-3 py-2 text-[11px] text-muted-foreground">
                    {r.connection_state ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {r.log ? (
                      <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-900">
                        log
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="max-w-[180px] truncate px-3 py-2 text-xs text-muted-foreground">
                    {r.comment ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => r.id && toggle.mutate({ id: r.id, disabled: !r.disabled })}
                      className="text-xs text-muted-foreground hover:underline"
                    >
                      {r.disabled ? "Enable" : "Disable"}
                    </button>
                    <button
                      onClick={() => {
                        if (r.id && confirm("Delete this rule?")) del.mutate(r.id);
                      }}
                      className="ml-3 text-xs text-destructive hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OrderButton({
  children,
  disabled,
  onClick,
  title,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="inline-flex size-6 items-center justify-center rounded border border-transparent text-[10px] text-muted-foreground transition hover:border-border hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}

function ActionPill({ action }: { action: string }) {
  const map: Record<string, string> = {
    accept: "bg-emerald-100 text-emerald-800",
    drop: "bg-red-100 text-red-800",
    reject: "bg-red-100 text-red-800",
    log: "bg-amber-100 text-amber-900",
    "fasttrack-connection": "bg-sky-100 text-sky-900",
  };
  const cls = map[action] ?? "bg-zinc-100 text-zinc-800";
  return (
    <span className={`inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>
      {action}
    </span>
  );
}

function RuleForm({
  deviceId,
  defaultChain,
  onCreated,
}: {
  deviceId: string;
  defaultChain: "input" | "forward" | "output";
  onCreated: () => void;
}) {
  const [chain, setChain] = useState<"input" | "forward" | "output">(defaultChain);
  const [action, setAction] = useState<string>("accept");
  const [srcAddress, setSrcAddress] = useState("");
  const [dstAddress, setDstAddress] = useState("");
  const [protocol, setProtocol] = useState("");
  const [srcPort, setSrcPort] = useState("");
  const [dstPort, setDstPort] = useState("");
  const [inIface, setInIface] = useState("");
  const [outIface, setOutIface] = useState("");
  const [connState, setConnState] = useState("");
  const [log, setLog] = useState(false);
  const [logPrefix, setLogPrefix] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createFilterRule(deviceId, {
        chain,
        action,
        src_address: srcAddress || null,
        dst_address: dstAddress || null,
        protocol: protocol || null,
        src_port: srcPort || null,
        dst_port: dstPort || null,
        in_interface: inIface || null,
        out_interface: outIface || null,
        connection_state: connState || null,
        log,
        log_prefix: logPrefix || null,
        comment: comment || null,
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    m.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="mt-4 rounded-lg border border-border bg-card p-5">
      {error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-4">
        <Field label="Chain" htmlFor="r-ch">
          <select
            id="r-ch"
            value={chain}
            onChange={(e) => setChain(e.target.value as typeof chain)}
            className={input}
          >
            {CHAINS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Action" htmlFor="r-ac">
          <select
            id="r-ac"
            value={action}
            onChange={(e) => setAction(e.target.value)}
            className={input}
          >
            {ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Protocol" htmlFor="r-pr">
          <input
            id="r-pr"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value)}
            className={`${input} font-mono`}
            placeholder="tcp / udp / icmp"
          />
        </Field>
        <Field label="Conn state" htmlFor="r-cs">
          <input
            id="r-cs"
            value={connState}
            onChange={(e) => setConnState(e.target.value)}
            className={`${input} font-mono`}
            placeholder="new,established"
          />
        </Field>
        <Field label="Src address" htmlFor="r-sa">
          <input
            id="r-sa"
            value={srcAddress}
            onChange={(e) => setSrcAddress(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.0/8"
          />
        </Field>
        <Field label="Dst address" htmlFor="r-da">
          <input
            id="r-da"
            value={dstAddress}
            onChange={(e) => setDstAddress(e.target.value)}
            className={`${input} font-mono`}
          />
        </Field>
        <Field label="Src port" htmlFor="r-sp">
          <input
            id="r-sp"
            value={srcPort}
            onChange={(e) => setSrcPort(e.target.value)}
            className={`${input} font-mono`}
          />
        </Field>
        <Field label="Dst port" htmlFor="r-dp">
          <input
            id="r-dp"
            value={dstPort}
            onChange={(e) => setDstPort(e.target.value)}
            className={`${input} font-mono`}
            placeholder="443 or 1000-2000"
          />
        </Field>
        <Field label="In iface" htmlFor="r-in">
          <input
            id="r-in"
            value={inIface}
            onChange={(e) => setInIface(e.target.value)}
            className={input}
          />
        </Field>
        <Field label="Out iface" htmlFor="r-out">
          <input
            id="r-out"
            value={outIface}
            onChange={(e) => setOutIface(e.target.value)}
            className={input}
          />
        </Field>
        <Field label="Comment" htmlFor="r-cm">
          <input
            id="r-cm"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={input}
          />
        </Field>
      </div>
      <div className="mt-4 flex items-center gap-6">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={log}
            onChange={(e) => setLog(e.target.checked)}
            className="size-4 rounded"
          />
          Log hits
        </label>
        {log && (
          <div className="max-w-xs">
            <input
              value={logPrefix}
              onChange={(e) => setLogPrefix(e.target.value)}
              className={`${input} font-mono`}
              placeholder="WG-PEER-INVALID"
            />
            <p className="mt-1 text-[11px] italic text-muted-foreground">
              Log prefix tagged on each matching packet (helps grep)
            </p>
          </div>
        )}
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Adding…" : "Add rule"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
