"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { EntryDetails, OutcomePill } from "@/components/audit-entry";
import { fullWhen, shortWhen } from "@/components/pager";
import {
  auditTarget,
  describeClient,
  getAuditSession,
  initials,
  revokeAuditSession,
  type AuditLogEntry,
  type AuditSession,
} from "@/lib/audit";
import { fetchMe, type UserPublic } from "@/lib/auth";

const DOT: Record<string, string> = {
  ok: "bg-emerald-500",
  denied: "bg-amber-500",
  failed: "bg-red-500",
};

function duration(fromIso: string, toIso: string): string {
  const mins = Math.max(0, Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60_000));
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  return `${h} h ${mins % 60} min`;
}

function relativeFuture(iso: string): string {
  const days = Math.round((new Date(iso).getTime() - Date.now()) / 86_400_000);
  if (days >= 1) return `in ${days} day${days === 1 ? "" : "s"}`;
  const hours = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000));
  return `in ${hours} h`;
}

function exportSession(s: AuditSession) {
  const blob = new Blob([JSON.stringify(s, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `netfleet-session-${s.session_id}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function AuditSessionPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState(false);

  const { data: s, isLoading, error } = useQuery<AuditSession>({
    queryKey: ["audit-session", id],
    queryFn: () => getAuditSession(id),
  });
  const { data: me } = useQuery<UserPublic | null>({ queryKey: ["me"], queryFn: fetchMe });

  const revoke = useMutation({
    mutationFn: () => revokeAuditSession(id),
    onSuccess: () => {
      setConfirmRevoke(false);
      qc.invalidateQueries({ queryKey: ["audit-session", id] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });

  // Newest first, like the audit log itself.
  const steps = useMemo(() => [...(s?.entries ?? [])].reverse(), [s]);
  const counts = useMemo(() => {
    const e = s?.entries ?? [];
    return {
      ok: e.filter((x) => x.outcome === "ok").length,
      denied: e.filter((x) => x.outcome === "denied").length,
      failed: e.filter((x) => x.outcome === "failed").length,
      devices: new Set(e.map((x) => x.device_id).filter(Boolean)).size,
    };
  }, [s]);

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading session…</p>;
  if (error || !s) {
    return (
      <div>
        <Link href="/dashboard/audit" className="text-xs font-semibold text-muted-foreground hover:text-foreground">
          ← Audit log
        </Link>
        <p className="mt-3 text-sm text-destructive">{(error as Error)?.message ?? "Session not found."}</p>
      </div>
    );
  }

  const who = s.user_name || s.user_email || "Unknown user";
  const ownSession = me?.id === s.user_id;
  const meta: { k: string; v: string; mono?: boolean }[] = [
    { k: "Started", v: s.started_at ? fullWhen(s.started_at) : "—", mono: true },
    { k: "Last activity", v: s.last_activity_at ? fullWhen(s.last_activity_at) : "—", mono: true },
    { k: "Sign-in method", v: s.sign_in_method ?? "—" },
    { k: "Source IP", v: s.ip_address ?? "—", mono: true },
    { k: "Client", v: describeClient(s.user_agent) },
    { k: "Role", v: s.role ?? "—" },
    { k: "Session ID", v: s.session_id, mono: true },
    {
      k: "Expires",
      v: s.active && s.expires_at ? `${relativeFuture(s.expires_at)} (refresh token)` : "Ended",
    },
  ];

  return (
    <div>
      <Link href="/dashboard/audit" className="text-xs font-semibold text-muted-foreground hover:text-foreground">
        ← Audit log
      </Link>

      <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-blue-100 text-base font-bold text-blue-700">
            {initials(s.user_name, s.user_email)}
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-2xl font-semibold tracking-tight">Session of {who}</h1>
              {s.active ? (
                <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Active
                </span>
              ) : (
                <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs font-semibold text-zinc-600">
                  Ended
                </span>
              )}
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {s.started_at && `Started ${shortWhen(s.started_at).toLowerCase()}`}
              {s.started_at && s.last_activity_at && ` · ${duration(s.started_at, s.last_activity_at)}`}
              {` · ${s.entries.length} ${s.entries.length === 1 ? "entry" : "entries"}`}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {s.previous_session_id && (
            <Link
              href={`/dashboard/audit/sessions/${s.previous_session_id}`}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              ‹ Previous session
            </Link>
          )}
          {s.next_session_id && (
            <Link
              href={`/dashboard/audit/sessions/${s.next_session_id}`}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              Next session ›
            </Link>
          )}
          <button
            type="button"
            onClick={() => exportSession(s)}
            className="rounded-md border border-border bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
          >
            Export
          </button>
          {me?.is_admin && s.active && !ownSession && (
            confirmRevoke ? (
              <>
                <span className="text-xs text-destructive">Sign this session out?</span>
                <button
                  type="button"
                  disabled={revoke.isPending}
                  onClick={() => revoke.mutate()}
                  className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {revoke.isPending ? "Revoking…" : "Yes, revoke"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmRevoke(false)}
                  className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent"
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmRevoke(true)}
                className="rounded-md border border-destructive/50 bg-background px-3 py-1.5 text-sm font-medium text-destructive hover:bg-destructive/10"
              >
                Revoke session
              </button>
            )
          )}
        </div>
      </div>
      {revoke.error && (
        <p className="mt-2 text-sm text-destructive">Revoke failed: {(revoke.error as Error).message}</p>
      )}

      <section className="mt-6 grid gap-4 rounded-lg border border-border bg-card p-4 [grid-template-columns:repeat(auto-fit,minmax(200px,1fr))]">
        {meta.map((m) => (
          <div key={m.k} className="min-w-0">
            <div className="text-xs text-muted-foreground">{m.k}</div>
            <div className={`mt-0.5 truncate text-sm font-semibold ${m.mono ? "font-mono" : ""}`} title={m.v}>
              {m.v}
            </div>
          </div>
        ))}
      </section>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-semibold">What happened in this session</h2>
        <div className="flex flex-wrap gap-1.5 text-xs">
          <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 font-semibold text-emerald-800">
            {counts.ok} success
          </span>
          {counts.denied > 0 && (
            <span className="rounded-full bg-amber-100 px-2.5 py-0.5 font-semibold text-amber-800">
              {counts.denied} denied
            </span>
          )}
          {counts.failed > 0 && (
            <span className="rounded-full bg-red-100 px-2.5 py-0.5 font-semibold text-red-800">
              {counts.failed} error
            </span>
          )}
          <span className="rounded-full bg-muted px-2.5 py-0.5 font-semibold text-muted-foreground">
            {counts.devices} {counts.devices === 1 ? "device" : "devices"} touched
          </span>
        </div>
      </div>

      <ol className="mt-3 rounded-lg border border-border bg-card">
        {steps.map((e, i) => (
          <Step
            key={e.id}
            entry={e}
            first={i === 0}
            expanded={expanded === e.id}
            onToggle={() => setExpanded(expanded === e.id ? null : e.id)}
          />
        ))}
      </ol>
    </div>
  );
}

/** A before → after pair, when the entry recorded one (firmware upgrades
 *  log `from` / `to`, edits log `before` / `after`). */
function diffOf(e: AuditLogEntry): [string, string] | null {
  const m = { ...(e.request_payload ?? {}), ...(e.response_meta ?? {}) } as Record<string, unknown>;
  for (const [a, b] of [
    ["from", "to"],
    ["before", "after"],
    ["from_version", "to_version"],
    ["current_version", "target_version"],
  ]) {
    const x = m[a];
    const y = m[b];
    if ((typeof x === "string" || typeof x === "number") && (typeof y === "string" || typeof y === "number")) {
      return [String(x), String(y)];
    }
  }
  return null;
}

function Step({
  entry: e,
  first,
  expanded,
  onToggle,
}: {
  entry: AuditLogEntry;
  first: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const diff = diffOf(e);
  const target = auditTarget(e);
  const where = [e.device_name ?? (target !== "—" ? target : null), e.site_name].filter(Boolean).join(" · ");
  return (
    <li className={`flex gap-4 px-4 py-3.5 ${first ? "" : "border-t border-border"}`}>
      <div className="w-14 shrink-0 pt-px font-mono text-xs text-muted-foreground">
        <time dateTime={e.ts} title={fullWhen(e.ts)}>
          {new Date(e.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}
        </time>
      </div>
      <div className="flex shrink-0 flex-col items-center">
        <span className={`mt-1 h-2.5 w-2.5 rounded-full ${DOT[e.outcome] ?? "bg-zinc-400"}`} />
        <span className="mt-1 w-0.5 flex-1 bg-border" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-semibold">
            {e.section}.{e.action}
          </span>
          <OutcomePill outcome={e.outcome} />
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            className="text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            {expanded ? "Hide details" : "Details"}
          </button>
        </div>
        {(where || e.error_message) && (
          <div className="mt-0.5 text-[13px] text-muted-foreground">
            {where}
            {e.error_message && (
              <span className="text-destructive">
                {where ? " · " : ""}
                {e.error_message}
              </span>
            )}
          </div>
        )}
        {diff && (
          <div className="mt-2 grid max-w-xl grid-cols-2 gap-2">
            <div className="rounded-md border border-red-200 bg-red-50 px-2.5 py-1.5 font-mono text-xs text-red-800">
              − {diff[0]}
            </div>
            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 font-mono text-xs text-emerald-800">
              + {diff[1]}
            </div>
          </div>
        )}
        {expanded && (
          <div className="mt-2 rounded-md bg-muted/30 px-3 py-2">
            <EntryDetails entry={e} />
          </div>
        )}
      </div>
    </li>
  );
}
