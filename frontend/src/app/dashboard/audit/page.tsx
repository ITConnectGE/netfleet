"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Fragment, useMemo, useState } from "react";

import { EntryDetails, OutcomePill } from "@/components/audit-entry";
import { Pager, TIME_RANGES, fullWhen, rangeStart, shortWhen } from "@/components/pager";
import {
  auditTarget,
  initials,
  queryAudit,
  type AuditLogEntry,
  type AuditOutcome,
  type AuditPage,
} from "@/lib/audit";

const DEFAULT_LIMIT = 50;
const ACTIONS = ["create", "update", "delete", "execute", "login", "clear_all", "acknowledge"];

type Mode = "entries" | "sessions";
type Day = "" | "today" | "yesterday";

function dayBounds(day: Day): { from?: string; to?: string } {
  if (!day) return {};
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  if (day === "yesterday") start.setDate(start.getDate() - 1);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { from: start.toISOString(), to: end.toISOString() };
}

interface Group {
  key: string;
  sessionId: string | null;
  rows: AuditLogEntry[];
}

/** Consecutive entries of one sign-in session (or one user's background
 *  rows) become a group. The page is newest first, so a session that was
 *  interleaved with another one shows up as two groups — that is the order
 *  things actually happened in. */
function groupBySession(items: AuditLogEntry[]): Group[] {
  const out: Group[] = [];
  for (const e of items) {
    const key = e.session_id ?? `none:${e.user_id ?? "system"}`;
    const last = out[out.length - 1];
    if (last && last.key === key) last.rows.push(e);
    else out.push({ key, sessionId: e.session_id, rows: [e] });
  }
  return out;
}

function minutesBetween(a: string, b: string): number {
  return Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 60_000));
}

export default function AuditLogPage() {
  const [mode, setMode] = useState<Mode>("sessions");
  const [search, setSearch] = useState("");
  const [range, setRange] = useState("all");
  const [day, setDay] = useState<Day>("");
  const [section, setSection] = useState("");
  const [action, setAction] = useState("");
  const [target, setTarget] = useState("");
  const [outcome, setOutcome] = useState<AuditOutcome | "">("");
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [expanded, setExpanded] = useState<string | null>(null);

  const bounds = dayBounds(day);
  const filters = {
    search: search || undefined,
    section: section || undefined,
    action: action || undefined,
    target: target || undefined,
    outcome: outcome || undefined,
    ts_from: bounds.from ?? rangeStart(range),
    ts_to: bounds.to,
    limit,
    offset,
  };

  const { data, isLoading, error } = useQuery<AuditPage>({
    queryKey: ["audit", filters],
    queryFn: () => queryAudit(filters),
    placeholderData: (prev) => prev,
  });

  const groups = useMemo(() => groupBySession(data?.items ?? []), [data]);
  const active = useMemo(() => new Set(data?.active_session_ids ?? []), [data]);

  const reset = () => {
    setSearch("");
    setRange("all");
    setDay("");
    setSection("");
    setAction("");
    setTarget("");
    setOutcome("");
    setOffset(0);
  };
  // Every filter change starts over at page one.
  const on =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v);
      setOffset(0);
    };

  const cols = mode === "entries" ? 8 : 7;
  const FILTER =
    "block w-full rounded border border-input bg-background px-1.5 py-0.5 text-[11px] font-normal text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every change made through NetFleet: who, what, when and from where.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div
            role="group"
            aria-label="Group by"
            className="inline-flex rounded-md border border-input bg-background p-0.5"
          >
            {(
              [
                ["entries", "Entries"],
                ["sessions", "By session"],
              ] as const
            ).map(([m, label]) => (
              <button
                key={m}
                type="button"
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
                className={`rounded px-3 py-1 text-xs font-medium transition ${
                  mode === m ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <input
            type="search"
            aria-label="Search audit log"
            value={search}
            onChange={(e) => on(setSearch)(e.target.value)}
            placeholder="Search user, section, target…"
            className="w-60 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <select
            aria-label="Time range"
            value={range}
            onChange={(e) => on(setRange)(e.target.value)}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
          >
            {TIME_RANGES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={reset}
            className="rounded-md px-2 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Reset filters
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      <div className="mt-4 overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-[13px]">
          <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th scope="col" className="w-8 px-2 py-2">
                <span className="sr-only">Details</span>
              </th>
              <th scope="col" className="w-32 px-2 py-2 font-medium">When</th>
              {mode === "entries" && <th scope="col" className="px-2 py-2 font-medium">User</th>}
              <th scope="col" className="px-2 py-2 font-medium">Section</th>
              <th scope="col" className="px-2 py-2 font-medium">Action</th>
              <th scope="col" className="px-2 py-2 font-medium">Target</th>
              <th scope="col" className="w-24 px-2 py-2 font-medium">Outcome</th>
              <th scope="col" className="w-20 px-2 py-2 font-medium">Session</th>
            </tr>
            <tr className="border-b border-border bg-muted/20">
              <td className="px-2 py-1" />
              <td className="px-2 py-1">
                <select
                  aria-label="Filter by day"
                  value={day}
                  onChange={(e) => on(setDay)(e.target.value as Day)}
                  className={FILTER}
                >
                  <option value="">Any</option>
                  <option value="today">Today</option>
                  <option value="yesterday">Yesterday</option>
                </select>
              </td>
              {mode === "entries" && <td className="px-2 py-1" />}
              <td className="px-2 py-1">
                <input
                  aria-label="Filter section"
                  value={section}
                  onChange={(e) => on(setSection)(e.target.value)}
                  placeholder="devices, sites…"
                  className={FILTER}
                />
              </td>
              <td className="px-2 py-1">
                <select
                  aria-label="Filter action"
                  value={action}
                  onChange={(e) => on(setAction)(e.target.value)}
                  className={FILTER}
                >
                  <option value="">Any</option>
                  {ACTIONS.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </td>
              <td className="px-2 py-1">
                <input
                  aria-label="Filter target"
                  value={target}
                  onChange={(e) => on(setTarget)(e.target.value)}
                  placeholder="name or id"
                  className={FILTER}
                />
              </td>
              <td className="px-2 py-1">
                <select
                  aria-label="Filter outcome"
                  value={outcome}
                  onChange={(e) => on(setOutcome)(e.target.value as AuditOutcome | "")}
                  className={FILTER}
                >
                  <option value="">Any</option>
                  <option value="ok">success</option>
                  <option value="denied">denied</option>
                  <option value="failed">error</option>
                </select>
              </td>
              <td className="px-2 py-1" />
            </tr>
          </thead>
          {isLoading && (
            <tbody>
              <tr>
                <td colSpan={cols} className="px-4 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            </tbody>
          )}
          {!isLoading && data && data.items.length === 0 && (
            <tbody>
              <tr>
                <td colSpan={cols} className="px-4 py-8 text-center text-muted-foreground">
                  No entries match the current filters.
                </td>
              </tr>
            </tbody>
          )}
          {mode === "entries" ? (
            <tbody className="divide-y divide-border">
              {data?.items.map((e) => (
                <EntryRows
                  key={e.id}
                  entry={e}
                  showUser
                  cols={cols}
                  expanded={expanded === e.id}
                  onToggle={() => setExpanded(expanded === e.id ? null : e.id)}
                />
              ))}
            </tbody>
          ) : (
            groups.map((g) => (
              <tbody key={`${g.key}-${g.rows[0].id}`} className="divide-y divide-border border-t border-border">
                <SessionHeader group={g} cols={cols} active={!!g.sessionId && active.has(g.sessionId)} />
                {g.rows.map((e) => (
                  <EntryRows
                    key={e.id}
                    entry={e}
                    cols={cols}
                    expanded={expanded === e.id}
                    onToggle={() => setExpanded(expanded === e.id ? null : e.id)}
                  />
                ))}
              </tbody>
            ))
          )}
        </table>
      </div>

      {data && (
        <div className="mt-3">
          <Pager
            offset={data.offset}
            limit={limit}
            total={data.total}
            onOffset={setOffset}
            onLimit={(n) => {
              setLimit(n);
              setOffset(0);
            }}
            limits={[25, 50, 100, 200]}
          />
        </div>
      )}
    </div>
  );
}

function SessionHeader({ group, cols, active }: { group: Group; cols: number; active: boolean }) {
  const first = group.rows[group.rows.length - 1];
  const last = group.rows[0];
  const system = !first.user_id;
  const who = system ? "Scheduled jobs" : first.user_name || first.user_email || "Unknown user";
  const mins = minutesBetween(first.ts, last.ts);
  const span =
    first.id === last.id
      ? shortWhen(first.ts)
      : `${shortWhen(first.ts)} – ${shortWhen(last.ts).replace(/^(Today|Yesterday) /, "")} (${mins} min)`;
  const login = group.rows.find((r) => r.section === "auth" && r.action === "login");
  const method = (login?.response_meta?.method as string | undefined) ?? null;
  const denied = group.rows.filter((r) => r.outcome === "denied").length;
  const count = group.rows.length === 1 ? "1 entry" : `${group.rows.length} entries`;

  return (
    <tr className="bg-muted/30">
      <td colSpan={cols} className="px-2 py-1.5">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${
              system ? "bg-zinc-200 text-zinc-600" : "bg-blue-100 text-blue-700"
            }`}
          >
            {system ? "SY" : initials(first.user_name, first.user_email)}
          </span>
          <span className="text-[13px] font-semibold text-foreground">{who}</span>
          {active && (
            <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-800">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Active
            </span>
          )}
          <span className="text-muted-foreground">
            {span}
            {method && ` · ${method}`}
            {first.ip_address && (
              <>
                {" · "}
                <span className="font-mono">{first.ip_address}</span>
              </>
            )}
            {` · ${count}`}
          </span>
          {denied > 0 && (
            <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">
              {denied} denied
            </span>
          )}
          {group.sessionId && (
            <Link
              href={`/dashboard/audit/sessions/${group.sessionId}`}
              className="ml-auto font-semibold text-primary hover:underline"
            >
              View session →
            </Link>
          )}
        </div>
      </td>
    </tr>
  );
}

function EntryRows({
  entry: e,
  cols,
  expanded,
  onToggle,
  showUser = false,
}: {
  entry: AuditLogEntry;
  cols: number;
  expanded: boolean;
  onToggle: () => void;
  showUser?: boolean;
}) {
  return (
    <Fragment>
      <tr className="hover:bg-accent/30">
        <td className="px-2 py-1">
          <button
            type="button"
            aria-label={expanded ? "Hide details" : "Show details"}
            aria-expanded={expanded}
            onClick={onToggle}
            className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className={`transition ${expanded ? "rotate-90" : ""}`}
            >
              <path d="m9 18 6-6-6-6" />
            </svg>
          </button>
        </td>
        <td className="whitespace-nowrap px-2 py-1 font-mono text-[11px] text-muted-foreground">
          <time dateTime={e.ts} title={fullWhen(e.ts)}>
            {shortWhen(e.ts)}
          </time>
        </td>
        {showUser && (
          <td className="max-w-[12rem] truncate px-2 py-1" title={e.user_email ?? undefined}>
            {e.user_id ? e.user_name || e.user_email : <span className="text-muted-foreground">Scheduled jobs</span>}
          </td>
        )}
        <td className="px-2 py-1 font-mono text-xs">{e.section}</td>
        <td className="px-2 py-1 font-mono text-xs">{e.action}</td>
        <td className="max-w-[14rem] truncate px-2 py-1 text-xs">{auditTarget(e)}</td>
        <td className="px-2 py-1">
          <OutcomePill outcome={e.outcome} />
        </td>
        <td className="px-2 py-1 text-xs">
          {e.session_id ? (
            <Link
              href={`/dashboard/audit/sessions/${e.session_id}`}
              aria-label="Open the session this entry belongs to"
              className="font-semibold text-primary hover:underline"
            >
              Open →
            </Link>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-muted/20">
          <td colSpan={cols} className="px-6 py-3">
            <EntryDetails entry={e} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}
