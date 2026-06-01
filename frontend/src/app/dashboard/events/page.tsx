"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  acknowledgeEvents,
  listEvents,
  type EventListResponse,
  type EventRow,
  type Severity,
} from "@/lib/events";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info"];
const PAGE_SIZE = 200;

interface ColDef {
  id: string;
  label: string;
  filterable: boolean;
  width?: string;
}

// Per-column header definitions. The filter row applies client-side
// substring matches on top of the server-fetched page.
const COLS: ColDef[] = [
  { id: "check", label: "", filterable: false, width: "w-10" },
  { id: "when", label: "When", filterable: true },
  { id: "severity", label: "Severity", filterable: true },
  { id: "topics", label: "Topics", filterable: true },
  { id: "device", label: "Device", filterable: true },
  { id: "tenant", label: "Tenant / Site", filterable: true },
  { id: "message", label: "Message", filterable: true },
  { id: "ack", label: "Ack", filterable: false },
];

export default function EventsPage() {
  const qc = useQueryClient();
  const router = useRouter();

  const [severity, setSeverity] = useState<Severity[]>(["critical", "error", "warning"]);
  const [showAcked, setShowAcked] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [colFilters, setColFilters] = useState<Record<string, string>>({});

  const { data, isLoading, error } = useQuery<EventListResponse>({
    queryKey: ["events", severity.join(","), showAcked, search, page],
    queryFn: () =>
      listEvents({
        severity: severity.length > 0 ? severity : undefined,
        acknowledged: showAcked ? undefined : false,
        search: search || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
    retry: (failureCount, err) => {
      // Auth errors keep failing — don't hammer the API.
      const msg = (err as Error)?.message?.toLowerCase() ?? "";
      if (msg.includes("token") || msg.includes("unauthorized") || msg.includes("401")) {
        return false;
      }
      return failureCount < 2;
    },
  });

  // The me query in the layout caches the user object, so an expired
  // session here never trips the layout's existing /login redirect.
  // Catch the typical auth failure messages and bounce manually.
  useEffect(() => {
    if (!error) return;
    const msg = (error as Error).message?.toLowerCase() ?? "";
    if (
      msg.includes("missing bearer token") ||
      msg.includes("invalid bearer token") ||
      msg.includes("token expired") ||
      msg.includes("unauthorized")
    ) {
      router.replace(
        `/login?next=${encodeURIComponent("/dashboard/events")}`,
      );
    }
  }, [error, router]);

  const ack = useMutation({
    mutationFn: (ids: string[]) => acknowledgeEvents(ids),
    onSuccess: () => {
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ["events"] });
    },
  });

  const rows = data?.rows ?? [];

  const filteredRows = useMemo(() => {
    const f = colFilters;
    return rows.filter((r) => {
      if (f.when) {
        const needle = f.when.toLowerCase();
        const display = new Date(r.observed_at).toLocaleString().toLowerCase();
        const devTime = (r.device_time ?? "").toLowerCase();
        if (!display.includes(needle) && !devTime.includes(needle)) return false;
      }
      if (f.severity && !r.severity.toLowerCase().includes(f.severity.toLowerCase())) {
        return false;
      }
      if (f.topics && !r.topics.toLowerCase().includes(f.topics.toLowerCase())) {
        return false;
      }
      if (f.device) {
        const needle = f.device.toLowerCase();
        if (!(r.device_name?.toLowerCase().includes(needle) ?? false)) {
          return false;
        }
      }
      if (f.tenant) {
        const needle = f.tenant.toLowerCase();
        const blob = [r.tenant_name, r.site_name]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!blob.includes(needle)) return false;
      }
      if (f.message && !r.message.toLowerCase().includes(f.message.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [rows, colFilters]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const allOnPageSelected =
    filteredRows.length > 0 && filteredRows.every((r) => selected.has(r.id));
  const toggleAllOnPage = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) filteredRows.forEach((r) => next.delete(r.id));
      else filteredRows.forEach((r) => next.add(r.id));
      return next;
    });
  };

  const onColFilter = (id: string, value: string) =>
    setColFilters((prev) => ({ ...prev, [id]: value }));

  const severityCounts = data?.by_severity;

  const toggleSev = (s: Severity) => {
    setPage(0);
    setSeverity((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s],
    );
  };

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Events</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Central inbox of critical / error / warning lines pulled from every
            enabled device. The worker scans on a 5-minute cycle.
          </p>
        </div>
        {data && (
          <div className="flex items-center gap-3 text-xs">
            <SummaryPill label="Critical" count={severityCounts?.critical ?? 0} sev="critical" />
            <SummaryPill label="Error" count={severityCounts?.error ?? 0} sev="error" />
            <SummaryPill label="Warning" count={severityCounts?.warning ?? 0} sev="warning" />
            <span className="text-muted-foreground">
              · {data.unacknowledged_total} unack
            </span>
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-3 rounded-lg border border-border bg-card p-3 md:grid-cols-[2fr_2fr_auto_auto]">
        <div>
          <span className="text-xs font-medium text-muted-foreground">Severity</span>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {SEVERITIES.map((s) => {
              const active = severity.includes(s);
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => toggleSev(s)}
                  className={`rounded-md px-2 py-1 text-xs font-medium transition ${
                    active ? severityChipActive(s) : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200"
                  }`}
                >
                  {s}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-muted-foreground" htmlFor="search">
            Search
          </label>
          <input
            id="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder="substring of message"
            className="mt-1 block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <label className="flex items-end gap-1.5 pb-1.5 text-xs">
          <input
            type="checkbox"
            checked={showAcked}
            onChange={(e) => {
              setShowAcked(e.target.checked);
              setPage(0);
            }}
          />
          <span>Include acknowledged</span>
        </label>
        <div className="flex items-end pb-1">
          <button
            disabled={selected.size === 0 || ack.isPending}
            onClick={() => ack.mutate(Array.from(selected))}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
          >
            {ack.isPending ? "Acking…" : `Acknowledge ${selected.size > 0 ? `(${selected.size})` : ""}`}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}
      {ack.error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Acknowledge failed: {(ack.error as Error).message}
        </div>
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              {COLS.map((c) => (
                <th
                  key={c.id}
                  className={`px-3 py-2 font-medium ${c.width ?? ""}`}
                >
                  {c.id === "check" ? (
                    <input
                      type="checkbox"
                      checked={allOnPageSelected}
                      onChange={toggleAllOnPage}
                      aria-label="Select all on this page"
                    />
                  ) : (
                    c.label
                  )}
                </th>
              ))}
            </tr>
            <tr className="border-b border-border bg-muted/20">
              {COLS.map((c) => (
                <th key={`${c.id}-f`} className="px-2 py-1 align-top">
                  {c.filterable ? (
                    <input
                      value={colFilters[c.id] ?? ""}
                      onChange={(e) => onColFilter(c.id, e.target.value)}
                      placeholder="filter…"
                      aria-label={`Filter ${c.label}`}
                      className="block w-full rounded border border-input bg-background px-2 py-0.5 text-[11px] font-normal text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring"
                    />
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={COLS.length} className="px-3 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && filteredRows.length === 0 && (
              <tr>
                <td colSpan={COLS.length} className="px-3 py-8 text-center text-muted-foreground">
                  {rows.length === 0
                    ? "No matching events. Either nothing has gone wrong (nice!), or the scanner has not run a tick yet (default cadence is 5 min)."
                    : "No rows match the column filters above."}
                </td>
              </tr>
            )}
            {filteredRows.map((r) => (
              <EventTr
                key={r.id}
                row={r}
                checked={selected.has(r.id)}
                onCheck={(c) =>
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (c) next.add(r.id);
                    else next.delete(r.id);
                    return next;
                  })
                }
              />
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {data
            ? `${filteredRows.length} of ${rows.length} on page · ${data.total} matching server-side`
            : ""}
        </span>
        <div className="flex items-center gap-2">
          <button
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="rounded-md border border-input bg-background px-2 py-1 disabled:opacity-50"
          >
            ← Prev
          </button>
          <span>
            page {page + 1} / {totalPages}
          </span>
          <button
            disabled={page + 1 >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-md border border-input bg-background px-2 py-1 disabled:opacity-50"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}

function EventTr({
  row,
  checked,
  onCheck,
}: {
  row: EventRow;
  checked: boolean;
  onCheck: (c: boolean) => void;
}) {
  const acked = row.acknowledged_at !== null;
  return (
    <tr className={`hover:bg-accent/30 ${acked ? "opacity-60" : ""}`}>
      <td className="px-3 py-2">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheck(e.target.checked)}
          disabled={acked}
          aria-label="select event"
        />
      </td>
      <td className="px-3 py-2 font-mono text-[11px]">
        {new Date(row.observed_at).toLocaleString()}
        {row.device_time && (
          <div className="text-[10px] text-muted-foreground">
            device: {row.device_time}
          </div>
        )}
      </td>
      <td className="px-3 py-2 text-xs">
        <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${severityChipActive(row.severity)}`}>
          {row.severity}
        </span>
      </td>
      <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{row.topics}</td>
      <td className="px-3 py-2 text-xs">
        {row.device_name ? (
          <Link
            href={`/dashboard/devices/${row.device_id}/logs`}
            className="hover:underline"
          >
            {row.device_name}
          </Link>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {row.tenant_name && row.site_name
          ? `${row.tenant_name} · ${row.site_name}`
          : row.tenant_name ?? row.site_name ?? "—"}
      </td>
      <td className="max-w-md px-3 py-2 font-mono text-[11px]">{row.message}</td>
      <td className="px-3 py-2 text-[10px]">
        {acked ? (
          <div className="text-emerald-700">
            ✓ {row.acknowledged_by_email ?? ""}
            <div className="text-muted-foreground">
              {row.acknowledged_at
                ? new Date(row.acknowledged_at).toLocaleString()
                : ""}
            </div>
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
    </tr>
  );
}

function SummaryPill({
  label,
  count,
  sev,
}: {
  label: string;
  count: number;
  sev: Severity;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 ${severityChipActive(sev)}`}
    >
      <span className="text-[10px] uppercase">{label}</span>
      <span className="font-mono font-semibold">{count}</span>
    </span>
  );
}

function severityChipActive(s: Severity): string {
  if (s === "critical") return "bg-red-200 text-red-900";
  if (s === "error") return "bg-red-100 text-red-800";
  if (s === "warning") return "bg-amber-100 text-amber-900";
  return "bg-zinc-100 text-zinc-700";
}
