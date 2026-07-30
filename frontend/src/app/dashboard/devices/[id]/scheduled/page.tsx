"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { getScheduledJobs, type ScheduledJob } from "@/lib/linux";
import { cn } from "@/lib/utils";

const SOURCE_LABEL: Record<string, string> = {
  "user-crontab": "User crontab",
  "system-crontab": "/etc/crontab",
  "cron.d": "/etc/cron.d",
  "run-parts": "cron.daily etc.",
  timer: "systemd timer",
};

export default function ScheduledPage() {
  const { id } = useParams<{ id: string }>();
  const [filter, setFilter] = useState("");
  const [source, setSource] = useState<string>("all");

  const { data, isLoading, error, refetch, isFetching } = useQuery<ScheduledJob[]>({
    queryKey: ["scheduled-jobs", id],
    queryFn: () => getScheduledJobs(id),
    enabled: Boolean(id),
  });

  const sources = useMemo(
    () => Array.from(new Set((data ?? []).map((j) => j.source))).sort(),
    [data],
  );

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (data ?? []).filter(
      (j) =>
        (source === "all" || j.source === source) &&
        (!needle ||
          j.command.toLowerCase().includes(needle) ||
          j.schedule.toLowerCase().includes(needle) ||
          (j.user ?? "").toLowerCase().includes(needle) ||
          (j.comment ?? "").toLowerCase().includes(needle)),
    );
  }, [data, filter, source]);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Scheduled jobs</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Crontabs and systemd timers together. On a current Ubuntu box much
            of what used to live in cron is now a timer, so showing only one
            would hide half of what actually runs.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="shrink-0 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          {isFetching ? "Reading…" : "Refresh"}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by command, schedule, user…"
          className="w-72 rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
        >
          <option value="all">All sources ({data?.length ?? 0})</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {SOURCE_LABEL[s] ?? s} (
              {(data ?? []).filter((j) => j.source === s).length})
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Reading…</p>}
      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </p>
      )}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/60 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Schedule</th>
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium">Runs</th>
                <th className="px-3 py-2 font-medium">Next</th>
                <th className="px-3 py-2 font-medium">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">
                    {data.length === 0
                      ? "Nothing scheduled on this host."
                      : "Nothing matches."}
                  </td>
                </tr>
              ) : (
                rows.map((j, idx) => (
                  <tr
                    key={`${j.origin}-${j.command}-${idx}`}
                    className={cn("hover:bg-accent/30", !j.enabled && "opacity-55")}
                  >
                    <td className="whitespace-nowrap px-3 py-2 align-top font-mono text-xs">
                      {j.schedule}
                      {!j.enabled && (
                        <span className="ml-2 rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-medium text-zinc-700">
                          disabled
                        </span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 align-top text-xs">
                      {j.user ?? "—"}
                    </td>
                    <td className="px-3 py-2 align-top">
                      <span className="block break-all font-mono text-xs">
                        {j.command}
                      </span>
                      {j.comment && j.comment !== j.command && (
                        <span className="mt-0.5 block text-[11px] text-muted-foreground">
                          {j.comment}
                        </span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 align-top text-xs text-muted-foreground">
                      {/* Only timers know their next run; cron does not
                          compute one until it fires. */}
                      {j.next_run_iso
                        ? new Date(j.next_run_iso).toLocaleString()
                        : "—"}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 align-top text-[11px] text-muted-foreground">
                      <span className="block">{SOURCE_LABEL[j.source] ?? j.source}</span>
                      {j.origin && (
                        <span className="block font-mono opacity-70" title={j.origin}>
                          {j.origin.length > 34
                            ? `…${j.origin.slice(-32)}`
                            : j.origin}
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {data && data.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Read-only for now. Editing schedules is coming with the same
          confirmation flow as the other write operations.
        </p>
      )}
    </section>
  );
}
