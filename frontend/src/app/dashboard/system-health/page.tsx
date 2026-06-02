"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import {
  fetchHostHealth,
  fetchHostHistory,
  formatBytes,
  formatBytesPerSec,
  type HistoryPoint,
  type HostHealth,
  type HostHistory,
} from "@/lib/host-health";

/**
 * NetFleet server health — CPU / memory / disk / network for the API
 * host itself plus the live outbound-connection peer list. Live values
 * refresh every 5 s; the historical sparkline is read once on mount
 * and re-fetched on a slower 60 s cadence to match the back-end
 * sampler.
 */
export default function SystemHealthPage() {
  const { data: live, error: liveError } = useQuery<HostHealth>({
    queryKey: ["host-health"],
    queryFn: fetchHostHealth,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
  });
  const { data: history } = useQuery<HostHistory>({
    queryKey: ["host-history"],
    queryFn: () => fetchHostHistory(240),
    refetchInterval: 60_000,
  });

  const points = history?.points ?? [];

  // Throughput per sample interval — derived from the cumulative
  // counters. Skip the first row because the first delta needs a
  // prior point to subtract from.
  const throughput = useMemo(() => {
    if (points.length < 2) return [] as { t: string; rx: number; tx: number }[];
    const out: { t: string; rx: number; tx: number }[] = [];
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const cur = points[i];
      const dt =
        (new Date(cur.sampled_at).getTime() -
          new Date(prev.sampled_at).getTime()) /
        1000;
      const safe = dt > 0 ? dt : 1;
      out.push({
        t: cur.sampled_at,
        rx: Math.max(0, (cur.net_rx_bytes - prev.net_rx_bytes) / safe),
        tx: Math.max(0, (cur.net_tx_bytes - prev.net_tx_bytes) / safe),
      });
    }
    return out;
  }, [points]);

  const lastThroughput = throughput.length
    ? throughput[throughput.length - 1]
    : null;

  return (
    <div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          NetFleet server health
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Live resource usage of the host running this NetFleet API. Sampled
          to the database every 60 s — history is capped at ≈ 5 MB.
        </p>
      </div>

      {liveError && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(liveError as Error).message}
        </div>
      )}

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <Gauge
          label="CPU"
          percent={live?.cpu_percent ?? 0}
          detail={`${live?.cpu_count ?? 0} cores`}
          color="primary"
        />
        <Gauge
          label="Memory"
          percent={live?.memory_percent ?? 0}
          detail={`${formatBytes(live?.memory_used_bytes ?? 0)} / ${formatBytes(
            live?.memory_total_bytes ?? 0,
          )}`}
          color="emerald"
        />
        <Gauge
          label="Disk (root)"
          percent={live?.disk_percent ?? 0}
          detail={`${formatBytes(live?.disk_used_bytes ?? 0)} / ${formatBytes(
            live?.disk_total_bytes ?? 0,
          )}`}
          color="amber"
        />
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <ChartCard
          title="CPU %"
          accent="#3b82f6"
          values={points.map((p) => p.cpu_percent)}
          unit="%"
          max={100}
          latest={live?.cpu_percent ?? 0}
          formatLatest={(v) => `${v.toFixed(1)} %`}
        />
        <ChartCard
          title="Memory used"
          accent="#10b981"
          values={points.map((p) => p.memory_used_bytes)}
          unit="bytes"
          max={live?.memory_total_bytes ?? undefined}
          latest={live?.memory_used_bytes ?? 0}
          formatLatest={(v) => formatBytes(v)}
        />
        <ChartCard
          title="Network throughput"
          accent="#a855f7"
          values={throughput.map((t) => t.rx + t.tx)}
          unit="bps"
          latest={lastThroughput ? lastThroughput.rx + lastThroughput.tx : 0}
          formatLatest={(v) => formatBytesPerSec(v)}
          subtitle={
            lastThroughput
              ? `↓ ${formatBytesPerSec(lastThroughput.rx)}  ·  ↑ ${formatBytesPerSec(
                  lastThroughput.tx,
                )}`
              : undefined
          }
        />
      </div>

      <NicTable live={live} />

      <PeerTable live={live} />

      {history && (
        <p className="mt-3 text-[11px] text-muted-foreground">
          History: {history.capacity.rows.toLocaleString()} samples · {formatBytes(
            history.capacity.approx_bytes,
          )}{" "}
          of {formatBytes(history.capacity.cap_bytes)} cap.
        </p>
      )}
    </div>
  );
}

function Gauge({
  label,
  percent,
  detail,
  color,
}: {
  label: string;
  percent: number;
  detail: string;
  color: "primary" | "emerald" | "amber";
}) {
  const safe = Math.max(0, Math.min(100, percent));
  const ringColor =
    safe > 85
      ? "stroke-red-500"
      : safe > 70
        ? "stroke-amber-500"
        : color === "primary"
          ? "stroke-blue-500"
          : color === "emerald"
            ? "stroke-emerald-500"
            : "stroke-amber-500";
  const circ = 2 * Math.PI * 42;
  const offset = circ - (safe / 100) * circ;
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-center gap-4">
        <svg viewBox="0 0 100 100" className="size-20">
          <circle
            cx="50"
            cy="50"
            r="42"
            className="stroke-muted"
            strokeWidth="8"
            fill="none"
          />
          <circle
            cx="50"
            cy="50"
            r="42"
            className={`${ringColor} transition-[stroke-dashoffset]`}
            strokeWidth="8"
            fill="none"
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            transform="rotate(-90 50 50)"
          />
          <text
            x="50"
            y="55"
            textAnchor="middle"
            className="fill-foreground text-base font-semibold"
          >
            {safe.toFixed(0)}%
          </text>
        </svg>
        <div className="min-w-0">
          <div className="text-sm font-medium">{label}</div>
          <div className="mt-0.5 text-xs text-muted-foreground">{detail}</div>
        </div>
      </div>
    </div>
  );
}

function ChartCard({
  title,
  values,
  accent,
  unit,
  max,
  latest,
  formatLatest,
  subtitle,
}: {
  title: string;
  values: number[];
  accent: string;
  unit: string;
  max?: number;
  latest: number;
  formatLatest: (n: number) => string;
  subtitle?: string;
}) {
  const path = useMemo(() => {
    if (values.length === 0) return "";
    const top = max ?? Math.max(...values, 1);
    const w = 240;
    const h = 60;
    const step = values.length > 1 ? w / (values.length - 1) : 0;
    return values
      .map((v, i) => {
        const x = i * step;
        const y = h - (Math.max(0, Math.min(top, v)) / top) * h;
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [values, max]);

  const area = useMemo(() => {
    if (!path) return "";
    return `${path} L240,60 L0,60 Z`;
  }, [path]);

  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="font-mono text-xs text-muted-foreground">
          {formatLatest(latest)}
        </span>
      </div>
      {subtitle && (
        <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p>
      )}
      <div className="mt-3 h-[60px] w-full">
        {values.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[11px] italic text-muted-foreground">
            Waiting for first sample…
          </div>
        ) : (
          <svg viewBox="0 0 240 60" preserveAspectRatio="none" className="size-full">
            <path d={area} fill={accent} opacity="0.12" />
            <path d={path} fill="none" stroke={accent} strokeWidth="1.5" />
          </svg>
        )}
      </div>
      <p className="mt-1 text-[10px] text-muted-foreground">
        Last {values.length} samples · {unit}
      </p>
    </div>
  );
}

function NicTable({ live }: { live: HostHealth | undefined }) {
  const nics = (live?.nics ?? []).filter((n) => !n.name.startsWith("lo"));
  if (!live) return null;
  return (
    <section className="mt-6 rounded-lg border border-border bg-card p-5">
      <h2 className="text-base font-semibold">Network interfaces</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Cumulative byte counters since the box booted, plus link state. Loopback
        is hidden.
      </p>
      <div className="mt-3 overflow-hidden rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Interface</th>
              <th className="px-3 py-2 font-medium">IPv4</th>
              <th className="px-3 py-2 font-medium">Link</th>
              <th className="px-3 py-2 font-medium text-right">RX bytes</th>
              <th className="px-3 py-2 font-medium text-right">TX bytes</th>
              <th className="px-3 py-2 font-medium text-right">Errors</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {nics.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  className="px-3 py-4 text-center text-xs text-muted-foreground"
                >
                  No interfaces reported.
                </td>
              </tr>
            )}
            {nics.map((n) => (
              <tr key={n.name} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-mono text-xs">{n.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{n.ipv4 ?? "—"}</td>
                <td className="px-3 py-2 text-xs">
                  {n.is_up ? (
                    <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800">
                      up · {n.speed_mbps || "?"} Mb/s
                    </span>
                  ) : (
                    <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-700">
                      down
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatBytes(n.rx_bytes)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatBytes(n.tx_bytes)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-[11px] text-muted-foreground">
                  in {n.errors_in} · out {n.errors_out}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PeerTable({ live }: { live: HostHealth | undefined }) {
  const peers = live?.peers ?? [];
  if (!live) return null;
  return (
    <section className="mt-6 rounded-lg border border-border bg-card p-5">
      <h2 className="text-base font-semibold">Live peers</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Open TCP connections grouped by remote IP. Useful for &ldquo;what is
        NetFleet talking to right now&rdquo;. Per-IP byte history needs
        kernel-side counters (iptables / nftables) that aren&apos;t available
        inside the unprivileged container — the cumulative RX/TX above is the
        answer for that.
      </p>
      <div className="mt-3 overflow-hidden rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Remote IP</th>
              <th className="px-3 py-2 font-medium text-right">Connections</th>
              <th className="px-3 py-2 font-medium">State breakdown</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {peers.length === 0 && (
              <tr>
                <td
                  colSpan={3}
                  className="px-3 py-4 text-center text-xs text-muted-foreground"
                >
                  No outbound connections — either the box is idle or
                  CAP_SYS_PTRACE isn&apos;t granted.
                </td>
              </tr>
            )}
            {peers.slice(0, 50).map((p) => (
              <tr key={p.remote} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-mono text-xs">{p.remote}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{p.count}</td>
                <td className="px-3 py-2 text-xs">
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(p.by_state).map(([state, count]) => (
                      <span
                        key={state}
                        className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${
                          state === "ESTABLISHED"
                            ? "bg-emerald-100 text-emerald-800"
                            : state === "TIME_WAIT"
                              ? "bg-zinc-100 text-zinc-700"
                              : "bg-amber-100 text-amber-800"
                        }`}
                      >
                        {state} · {count}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
            {peers.length > 50 && (
              <tr>
                <td
                  colSpan={3}
                  className="px-3 py-2 text-center text-[11px] italic text-muted-foreground"
                >
                  …and {peers.length - 50} more remotes.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// Suppress unused HistoryPoint warning — it's re-exported through the
// public API of @/lib/host-health.
export type _HistoryPoint = HistoryPoint;
