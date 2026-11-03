"use client";

import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";

import { queryAudit, type AuditFilters, type AuditOutcome, type AuditPage } from "@/lib/audit";

const PAGE_SIZE = 50;

export default function AuditPage() {
  const [filters, setFilters] = useState<AuditFilters>({ limit: PAGE_SIZE, offset: 0 });
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading } = useQuery<AuditPage>({
    queryKey: ["audit", filters],
    queryFn: () => queryAudit(filters),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every privileged action across NetFleet. Click a row to see the request payload.
      </p>

      <div className="mt-6 grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-5">
        <FilterInput
          label="Section"
          value={filters.section ?? ""}
          onChange={(v) => setFilters({ ...filters, section: v || undefined, offset: 0 })}
          placeholder="devices, sites, …"
        />
        <FilterInput
          label="Action"
          value={filters.action ?? ""}
          onChange={(v) => setFilters({ ...filters, action: v || undefined, offset: 0 })}
          placeholder="create, update, …"
        />
        <FilterSelect
          label="Outcome"
          value={filters.outcome ?? ""}
          onChange={(v) =>
            setFilters({
              ...filters,
              outcome: (v as AuditOutcome) || undefined,
              offset: 0,
            })
          }
          options={[
            { value: "", label: "any" },
            { value: "ok", label: "ok" },
            { value: "denied", label: "denied" },
            { value: "failed", label: "failed" },
          ]}
        />
        <FilterInput
          label="User ID"
          value={filters.user_id ?? ""}
          onChange={(v) => setFilters({ ...filters, user_id: v || undefined, offset: 0 })}
          placeholder="uuid"
        />
        <FilterInput
          label="Device ID"
          value={filters.device_id ?? ""}
          onChange={(v) => setFilters({ ...filters, device_id: v || undefined, offset: 0 })}
          placeholder="uuid"
        />
      </div>

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Timestamp</th>
              <th className="px-4 py-2.5 font-medium">User</th>
              <th className="px-4 py-2.5 font-medium">Section</th>
              <th className="px-4 py-2.5 font-medium">Action</th>
              <th className="px-4 py-2.5 font-medium">Outcome</th>
              <th className="px-4 py-2.5 font-medium">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && data && data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  No events match the current filters.
                </td>
              </tr>
            )}
            {data?.items.map((e) => (
              <Fragment key={e.id}>
                <tr
                  onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                  className="cursor-pointer hover:bg-accent/30"
                >
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                    {new Date(e.ts).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5">{e.user_email ?? "—"}</td>
                  <td className="px-4 py-2.5 font-mono text-xs">{e.section}</td>
                  <td className="px-4 py-2.5 font-mono text-xs">{e.action}</td>
                  <td className="px-4 py-2.5">
                    <OutcomePill outcome={e.outcome} />
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                    {e.ip_address ?? "—"}
                  </td>
                </tr>
                {expanded === e.id && (
                  <tr className="bg-muted/20">
                    <td colSpan={6} className="px-6 py-4">
                      <Detail label="User agent">
                        <span className="font-mono text-xs">{e.user_agent ?? "—"}</span>
                      </Detail>
                      {e.device_id && (
                        <Detail label="Device">
                          <span className="font-mono text-xs">{e.device_id}</span>
                        </Detail>
                      )}
                      {e.site_id && (
                        <Detail label="Site">
                          <span className="font-mono text-xs">{e.site_id}</span>
                        </Detail>
                      )}
                      {e.request_payload && (
                        <Detail label="Request">
                          <pre className="mt-1 overflow-x-auto rounded-md bg-background p-2 font-mono text-xs">
                            {JSON.stringify(e.request_payload, null, 2)}
                          </pre>
                        </Detail>
                      )}
                      {e.response_meta && (
                        <Detail label="Response">
                          <pre className="mt-1 overflow-x-auto rounded-md bg-background p-2 font-mono text-xs">
                            {JSON.stringify(e.response_meta, null, 2)}
                          </pre>
                        </Detail>
                      )}
                      {e.error_message && (
                        <Detail label="Error">
                          <span className="font-mono text-xs text-destructive">
                            {e.error_message}
                          </span>
                        </Detail>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {data && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {data.total === 0
              ? "0 events"
              : `${data.offset + 1}–${Math.min(data.offset + data.items.length, data.total)} of ${data.total}`}
          </span>
          <Pager
            offset={data.offset}
            total={data.total}
            onOffset={(offset) => setFilters({ ...filters, offset })}
          />
        </div>
      )}
    </div>
  );
}

function OutcomePill({ outcome }: { outcome: AuditOutcome }) {
  const cls =
    outcome === "ok"
      ? "bg-emerald-100 text-emerald-800"
      : outcome === "denied"
        ? "bg-amber-100 text-amber-800"
        : "bg-red-100 text-red-800";
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${cls}`}>
      {outcome}
    </span>
  );
}

function FilterInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block space-y-1 text-xs font-medium text-muted-foreground">
      {label}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </label>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="block space-y-1 text-xs font-medium text-muted-foreground">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="py-1.5">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-0.5">{children}</div>
    </div>
  );
}

const PAGER_BTN =
  "rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium transition hover:bg-accent disabled:opacity-50";

function Pager({
  offset,
  total,
  onOffset,
}: {
  offset: number;
  total: number;
  onOffset: (offset: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const current = Math.floor(offset / PAGE_SIZE) + 1;
  const go = (page: number) =>
    onOffset((Math.min(Math.max(page, 1), pages) - 1) * PAGE_SIZE);
  const [draft, setDraft] = useState<string | null>(null);
  const atFirst = current <= 1;
  const atLast = current >= pages;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button disabled={atFirst} onClick={() => go(1)} className={PAGER_BTN} title="First page">
        « First
      </button>
      <button disabled={atFirst} onClick={() => go(current - 1)} className={PAGER_BTN}>
        ← Previous
      </button>
      <form
        className="flex items-center gap-1 text-xs text-muted-foreground"
        onSubmit={(e) => {
          e.preventDefault();
          const n = Number.parseInt(draft ?? "", 10);
          if (Number.isFinite(n)) go(n);
          setDraft(null);
        }}
      >
        <span>Page</span>
        <input
          aria-label="Go to page"
          inputMode="numeric"
          value={draft ?? String(current)}
          onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, ""))}
          onBlur={() => setDraft(null)}
          className="w-12 rounded-md border border-input bg-background px-1.5 py-1 text-center text-xs text-foreground"
        />
        <span>of {pages}</span>
      </form>
      <button disabled={atLast} onClick={() => go(current + 1)} className={PAGER_BTN}>
        Next →
      </button>
      <button disabled={atLast} onClick={() => go(pages)} className={PAGER_BTN} title="Last page">
        Last »
      </button>
    </div>
  );
}
