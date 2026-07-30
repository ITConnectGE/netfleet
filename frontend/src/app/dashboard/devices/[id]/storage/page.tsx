"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { UsageBar } from "@/components/usage-bar";
import {
  formatBytes,
  getDisks,
  type DiskUsage,
} from "@/lib/resources";

export default function StoragePage() {
  const { id } = useParams<{ id: string }>();

  const { data, isLoading, error, refetch, isFetching } = useQuery<DiskUsage[]>({
    queryKey: ["disks", id],
    queryFn: () => getDisks(id),
    enabled: Boolean(id),
  });

  return (
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Storage</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Mounted filesystems, read live from the host. Pseudo-filesystems
            (tmpfs, squashfs, overlay) are hidden — they report sizes nobody
            can act on.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="shrink-0 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          {isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {isLoading && (
        <p className="text-sm text-muted-foreground">Reading filesystems…</p>
      )}
      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </p>
      )}

      {data && data.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No real filesystems reported.
        </p>
      )}

      {data && data.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">
          {data.map((d) => (
            <div
              key={d.mount_point}
              className="rounded-lg border border-border bg-card p-4"
            >
              <div className="flex items-baseline justify-between gap-2">
                <p className="font-mono text-sm font-medium">{d.mount_point}</p>
                <p className="text-[11px] text-muted-foreground">{d.fs_type}</p>
              </div>
              <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">
                {d.filesystem}
              </p>

              <UsageBar
                className="mt-3"
                label="Space"
                pct={d.used_pct}
                detail={`${formatBytes(d.used_bytes)} used · ${formatBytes(
                  d.available_bytes,
                )} free of ${formatBytes(d.total_bytes)}`}
              />

              {/* Inodes get equal billing on purpose: a filesystem can be at
                  30% of its bytes and still refuse every write. */}
              {d.inodes_total != null && (
                <UsageBar
                  className="mt-3"
                  label="Inodes"
                  pct={d.inodes_used_pct}
                  detail={`${d.inodes_used?.toLocaleString() ?? "—"} of ${d.inodes_total.toLocaleString()}`}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
