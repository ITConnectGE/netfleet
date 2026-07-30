"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { getProcesses, type ProcessInfo } from "@/lib/linux";
import { formatBytes } from "@/lib/resources";
import { cn } from "@/lib/utils";

type SortKey = "cpu_pct" | "mem_pct" | "rss_bytes" | "pid";

export default function ProcessesPage() {
  const { id } = useParams<{ id: string }>();
  const [limit, setLimit] = useState(40);
  const [sort, setSort] = useState<SortKey>("cpu_pct");
  const [filter, setFilter] = useState("");
  const [live, setLive] = useState(false);

  const { data, isLoading, error, refetch, isFetching } = useQuery<ProcessInfo[]>({
    queryKey: ["processes", id, limit],
    queryFn: () => getProcesses(id, limit),
    enabled: Boolean(id),
    // Off by default: each refresh is an SSH round trip, so a permanently
    // live table would keep a connection churning on every open browser.
    refetchInterval: live ? 5_000 : false,
  });

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const list = (data ?? []).filter(
      (p) =>
        !needle ||
        p.command.toLowerCase().includes(needle) ||
        (p.user ?? "").toLowerCase().includes(needle) ||
        String(p.pid) === needle,
    );
    return [...list].sort((a, b) =>
      sort === "pid" ? a.pid - b.pid : (b[sort] ?? 0) - (a[sort] ?? 0),
    );
  }, [data, filter, sort]);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Processes</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Read live over SSH. CPU% is the average over each process&apos;s
            lifetime, the way <code className="font-mono text-xs">ps</code>{" "}
            reports it — not an instantaneous sample like{" "}
            <code className="font-mono text-xs">htop</code>, so a long-running
            daemon looks calmer than it may be right now.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={live}
              onChange={(e) => setLive(e.target.checked)}
              className="size-3.5 rounded"
            />
            Auto-refresh
          </label>
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            {isFetching ? "Reading…" : "Refresh"}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by command, user or PID…"
          className="w-64 rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
        >
          <option value="cpu_pct">Sort by CPU</option>
          <option value="mem_pct">Sort by memory %</option>
          <option value="rss_bytes">Sort by RSS</option>
          <option value="pid">Sort by PID</option>
        </select>
        <select
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="rounded-md border border-input bg-background px-2 py-1.5 text-sm"
        >
          {[20, 40, 100, 200].map((n) => (
            <option key={n} value={n}>
              Top {n}
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
                <th className="px-3 py-2 font-medium">PID</th>
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 text-right font-medium">CPU%</th>
                <th className="px-3 py-2 text-right font-medium">MEM%</th>
                <th className="px-3 py-2 text-right font-medium">RSS</th>
                <th className="px-3 py-2 font-medium">Thr</th>
                <th className="px-3 py-2 font-medium">State</th>
                <th className="px-3 py-2 font-medium">Time</th>
                <th className="px-3 py-2 font-medium">Command</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-3 py-6 text-center text-muted-foreground">
                    Nothing matches.
                  </td>
                </tr>
              ) : (
                rows.map((p) => (
                  <tr key={p.pid} className="hover:bg-accent/30">
                    <td className="px-3 py-1.5 font-mono text-xs">{p.pid}</td>
                    <td className="px-3 py-1.5 text-xs">{p.user}</td>
                    <td
                      className={cn(
                        "px-3 py-1.5 text-right font-mono text-xs tabular-nums",
                        (p.cpu_pct ?? 0) >= 50 && "font-semibold text-amber-700",
                        (p.cpu_pct ?? 0) >= 90 && "font-semibold text-destructive",
                      )}
                    >
                      {p.cpu_pct?.toFixed(1) ?? "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums">
                      {p.mem_pct?.toFixed(1) ?? "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-xs tabular-nums">
                      {formatBytes(p.rss_bytes)}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-xs">{p.threads ?? "—"}</td>
                    <td className="px-3 py-1.5 font-mono text-xs" title={p.started ?? ""}>
                      {p.state}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-xs">{p.cpu_time}</td>
                    <td
                      className="max-w-[32rem] truncate px-3 py-1.5 font-mono text-xs"
                      title={p.command}
                    >
                      {p.command}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
