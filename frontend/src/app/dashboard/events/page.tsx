"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Pager, TIME_RANGES, fullWhen, rangeStart, shortWhen } from "@/components/pager";
import { fetchMe, type UserPublic } from "@/lib/auth";
import { listDevices, type Device } from "@/lib/devices";
import {
  acknowledgeEvents,
  clearAllEvents,
  listEvents,
  type EventListResponse,
  type EventRow,
  type Severity,
} from "@/lib/events";
import { listSites, type Site } from "@/lib/sites";
import { listTenants, type Tenant } from "@/lib/tenants";

const SEVERITIES: Severity[] = ["critical", "error", "warning", "info"];
const DEFAULT_LIMIT = 50;

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
  { id: "severity", label: "Severity", filterable: false, width: "w-20" },
  { id: "when", label: "Observed", filterable: true, width: "w-32" },
  { id: "tenant", label: "Tenant", filterable: true },
  { id: "site", label: "Site", filterable: true },
  { id: "device", label: "Device", filterable: true },
  { id: "topics", label: "Topic", filterable: true },
  { id: "message", label: "Message", filterable: true },
  { id: "ack", label: "Ack", filterable: false },
];

export default function EventsPage() {
  const qc = useQueryClient();
  const router = useRouter();

  // Default to "show everything" — events page is a unified log inbox,
  // not just an alert console. Operators who only want red flags can
  // un-tick info / warning; we don't want a fresh visit to look empty.
  const [severity, setSeverity] = useState<Severity[]>([
    "critical",
    "error",
    "warning",
    "info",
  ]);
  const [showAcked, setShowAcked] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [tenantId, setTenantId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [range, setRange] = useState("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [colFilters, setColFilters] = useState<Record<string, string>>({});

  const { data, isLoading, error } = useQuery<EventListResponse>({
    queryKey: [
      "events",
      severity.join(","),
      showAcked,
      search,
      page,
      limit,
      tenantId,
      siteId,
      deviceId,
      range,
    ],
    queryFn: () =>
      listEvents({
        severity: severity.length > 0 ? severity : undefined,
        acknowledged: showAcked ? undefined : false,
        search: search || undefined,
        tenant_id: tenantId || undefined,
        site_id: siteId || undefined,
        device_id: deviceId || undefined,
        since: rangeStart(range),
        limit,
        offset: page * limit,
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

  const { data: me } = useQuery<UserPublic | null>({
    queryKey: ["me"],
    queryFn: fetchMe,
  });
  const [confirmClear, setConfirmClear] = useState(false);
  const clearAll = useMutation({
    mutationFn: clearAllEvents,
    onSuccess: () => {
      setConfirmClear(false);
      setSelected(new Set());
      setPage(0);
      qc.invalidateQueries({ queryKey: ["events"] });
    },
  });

  const { data: tenants } = useQuery<Tenant[]>({ queryKey: ["tenants"], queryFn: listTenants });
  const { data: sites } = useQuery<Site[]>({ queryKey: ["sites"], queryFn: () => listSites() });
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const siteOptions = useMemo(
    () => (sites ?? []).filter((s) => !tenantId || s.tenant_id === tenantId),
    [sites, tenantId],
  );
  const deviceOptions = useMemo(() => {
    const siteIds = new Set(siteOptions.map((s) => s.id));
    return (devices ?? []).filter((d) =>
      siteId ? d.site_id === siteId : !tenantId || siteIds.has(d.site_id),
    );
  }, [devices, siteOptions, siteId, tenantId]);

  const resetFilters = () => {
    setSeverity([...SEVERITIES]);
    setShowAcked(false);
    setSearch("");
    setTenantId("");
    setSiteId("");
    setDeviceId("");
    setRange("all");
    setColFilters({});
    setPage(0);
  };

  // Memoise so the empty-array fallback doesn't churn useMemo on every
  // render before the first fetch resolves.
  const rows = useMemo<EventRow[]>(() => data?.rows ?? [], [data]);

  const filteredRows = useMemo(() => {
    const f = colFilters;
    return rows.filter((r) => {
      if (f.when) {
        const needle = f.when.toLowerCase();
        const display = `${shortWhen(r.observed_at)} ${fullWhen(r.observed_at)}`.toLowerCase();
        const devTime = (r.device_time ?? "").toLowerCase();
        if (!display.includes(needle) && !devTime.includes(needle)) return false;
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
      if (f.tenant && !(r.tenant_name ?? "").toLowerCase().includes(f.tenant.toLowerCase())) {
        return false;
      }
      if (f.site && !(r.site_name ?? "").toLowerCase().includes(f.site.toLowerCase())) {
        return false;
      }
      if (f.message && !r.message.toLowerCase().includes(f.message.toLowerCase())) {
        return false;
      }
      return true;
    });
  }, [rows, colFilters]);

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
            Unified log feed — every line every enabled device emits, pulled
            into one inbox. Severity, device and free-text filters narrow it
            down; the worker scans on a 5-minute cycle.
          </p>
        </div>
        {data && (
          <div className="flex items-center gap-3 text-xs">
            <SummaryPill label="Critical" count={severityCounts?.critical ?? 0} sev="critical" />
            <SummaryPill label="Error" count={severityCounts?.error ?? 0} sev="error" />
            <SummaryPill label="Warning" count={severityCounts?.warning ?? 0} sev="warning" />
            <SummaryPill label="Info" count={severityCounts?.info ?? 0} sev="info" />
            <span className="text-muted-foreground">
              · {data.unacknowledged_total} unack
            </span>
          </div>
        )}
      </div>

      <div className="mt-4 space-y-3 rounded-lg border border-border bg-card p-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_1fr_2fr]">
          <label className="block text-xs font-medium text-muted-foreground">
            Tenant
            <select
              value={tenantId}
              onChange={(e) => {
                setTenantId(e.target.value);
                setSiteId("");
                setDeviceId("");
                setPage(0);
              }}
              className="mt-1 block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">All tenants</option>
              {(tenants ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Site
            <select
              value={siteId}
              onChange={(e) => {
                setSiteId(e.target.value);
                setDeviceId("");
                setPage(0);
              }}
              className="mt-1 block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">All sites</option>
              {siteOptions.map((st) => (
                <option key={st.id} value={st.id}>
                  {st.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Device
            <select
              value={deviceId}
              onChange={(e) => {
                setDeviceId(e.target.value);
                setPage(0);
              }}
              className="mt-1 block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="">All devices</option>
              {deviceOptions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Time range
            <select
              value={range}
              onChange={(e) => {
                setRange(e.target.value);
                setPage(0);
              }}
              className="mt-1 block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            >
              {TIME_RANGES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Message
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              placeholder="substring of message"
              className="mt-1 block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs font-medium text-muted-foreground">Severity</span>
            {SEVERITIES.map((s) => {
              const active = severity.includes(s);
              return (
                <button
                  key={s}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleSev(s)}
                  className={`rounded-md px-2 py-1 text-xs font-medium transition ${
                    active ? severityChipActive(s) : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200"
                  }`}
                >
                  {s}
                </button>
              );
            })}
            <label className="ml-2 flex items-center gap-1.5 text-xs">
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
            <button
              type="button"
              onClick={resetFilters}
              className="ml-2 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              Reset filters
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              disabled={selected.size === 0 || ack.isPending}
              onClick={() => ack.mutate(Array.from(selected))}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {ack.isPending
                ? "Acking…"
                : selected.size > 0
                  ? `Acknowledge (${selected.size})`
                  : "Acknowledge selected"}
            </button>
        {me?.is_admin && (
          <div className="flex items-center gap-2">
            {confirmClear ? (
              <>
                <span className="text-xs text-destructive">
                  Clear every event for all devices?
                </span>
                <button
                  disabled={clearAll.isPending}
                  onClick={() => clearAll.mutate()}
                  className="rounded-md bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {clearAll.isPending ? "Clearing…" : "Yes, clear all"}
                </button>
                <button
                  disabled={clearAll.isPending}
                  onClick={() => setConfirmClear(false)}
                  className="rounded-md border border-border px-3 py-1.5 text-xs hover:bg-accent/60"
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={() => setConfirmClear(true)}
                title="Admin only: remove every event from the inbox"
                className="rounded-md border border-destructive/50 px-3 py-1.5 text-xs font-medium text-destructive transition hover:bg-destructive/10"
              >
                Clear all
              </button>
            )}
          </div>
        )}
          </div>
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}
      {clearAll.error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Clear failed: {(clearAll.error as Error).message}
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

      {data && (
        <div className="mt-3 space-y-1">
          <Pager
            offset={page * limit}
            limit={limit}
            total={data.total}
            onOffset={(o) => setPage(Math.floor(o / limit))}
            onLimit={(n) => {
              setLimit(n);
              setPage(0);
            }}
            noun="events"
          />
          {filteredRows.length !== rows.length && (
            <p className="text-xs text-muted-foreground">
              Column filters show {filteredRows.length} of {rows.length} rows on this page.
            </p>
          )}
        </div>
      )}
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
      <td className="px-3 py-2 text-xs">
        <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${severityChipActive(row.severity)}`}>
          {row.severity}
        </span>
      </td>
      <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px]">
        <time
          dateTime={row.observed_at}
          title={`${fullWhen(row.observed_at)}${row.device_time ? ` · device: ${row.device_time}` : ""}`}
        >
          {shortWhen(row.observed_at)}
        </time>
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{row.tenant_name ?? "—"}</td>
      <td className="px-3 py-2 text-xs text-muted-foreground">{row.site_name ?? "—"}</td>
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
      <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{row.topics}</td>
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
