"use client";

import { useQuery } from "@tanstack/react-query";

import { UsageBar } from "@/components/usage-bar";
import {
  formatBytes,
  formatUptime,
  getResources,
  type SystemResources,
} from "@/lib/resources";

/**
 * Live CPU / memory / uptime for a host.
 *
 * Refetched on an interval rather than streamed: this is a "how is the box
 * right now" panel, and the historical series belongs in Zabbix. The
 * interval is deliberately unhurried — every poll is an SSH round trip.
 */
export function ResourcesCard({
  deviceId,
  pinned,
}: {
  deviceId: string;
  /** Host-key fingerprint. Absent means the device has never been tested,
   *  and every read will be refused, so we do not poll into a wall. */
  pinned?: string | null;
}) {
  const { data, isLoading, error, refetch, isFetching } =
    useQuery<SystemResources>({
      queryKey: ["resources", deviceId],
      queryFn: () => getResources(deviceId),
      enabled: Boolean(deviceId) && Boolean(pinned),
      refetchInterval: 30_000,
    });

  if (!pinned) {
    return (
      <section className="rounded-lg border border-amber-300 bg-amber-50/50 p-4 text-sm">
        <p className="font-medium text-amber-900">Host key not verified yet</p>
        <p className="mt-1 text-amber-800">
          Run <span className="font-medium">Test connection</span> to pin this
          server&apos;s SSH host key. Until then NetFleet will not run anything
          against it.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Resources</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Read live over SSH{data?.identity ? ` from ${data.identity}` : ""}.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="shrink-0 rounded-md border border-input bg-background px-2.5 py-1 text-xs font-medium hover:bg-accent disabled:opacity-50"
        >
          {isFetching ? "Reading…" : "Refresh"}
        </button>
      </div>

      {isLoading && (
        <p className="mt-3 text-sm text-muted-foreground">Reading…</p>
      )}
      {error && (
        <p className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {(error as Error).message}
        </p>
      )}

      {data && (
        <>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <UsageBar
              label={`CPU${data.cpu_count ? ` · ${data.cpu_count} cores` : ""}`}
              pct={data.cpu_load_pct}
              detail={
                data.load_avg_1 != null
                  ? `load ${data.load_avg_1} / ${data.load_avg_5 ?? "—"} / ${
                      data.load_avg_15 ?? "—"
                    }`
                  : undefined
              }
            />
            <UsageBar
              label="Memory"
              pct={data.memory_used_pct}
              detail={
                data.memory_total_bytes != null
                  ? `${formatBytes(data.memory_used_bytes)} of ${formatBytes(
                      data.memory_total_bytes,
                    )}`
                  : undefined
              }
            />
            {/* Swap only when the host actually has some — a zero-length bar
                on every cloud VPS is noise. */}
            {data.swap_total_bytes != null && data.swap_total_bytes > 0 && (
              <UsageBar
                label="Swap"
                pct={
                  (data.swap_used_bytes! / data.swap_total_bytes) * 100
                }
                detail={`${formatBytes(data.swap_used_bytes)} of ${formatBytes(
                  data.swap_total_bytes,
                )}`}
              />
            )}
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-foreground">Uptime</p>
              <p className="text-lg font-semibold tabular-nums">
                {formatUptime(data.uptime_seconds)}
              </p>
              {data.os_version && (
                <p className="text-[11px] text-muted-foreground">
                  {data.os_version}
                  {data.firmware ? ` · ${data.firmware}` : ""}
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
