"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

import { UsageBar } from "@/components/usage-bar";
import { getDiskTree, type DirEntryUsage } from "@/lib/linux";
import { formatBytes, getDisks, type DiskUsage } from "@/lib/resources";

export default function StoragePage() {
  const { id } = useParams<{ id: string }>();
  const [browsing, setBrowsing] = useState<string | null>(null);

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

              <button
                type="button"
                onClick={() =>
                  setBrowsing(browsing === d.mount_point ? null : d.mount_point)
                }
                className="mt-3 text-xs font-medium text-primary hover:underline"
              >
                {browsing === d.mount_point ? "Hide contents" : "Browse contents →"}
              </button>
            </div>
          ))}
        </div>
      )}

      {browsing && (
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-sm font-semibold">
              What is using space in{" "}
              <span className="font-mono">{browsing}</span>
            </h3>
            <button
              type="button"
              onClick={() => setBrowsing(null)}
              className="text-xs text-muted-foreground hover:underline"
            >
              Close
            </button>
          </div>
          <DirNode deviceId={id} path={browsing} depth={0} defaultOpen />
        </div>
      )}
    </section>
  );
}

/**
 * One expandable directory. Children are fetched only when the node is
 * opened — `du` over a whole filesystem takes minutes, and almost all of
 * that work is for branches nobody looks at.
 */
function DirNode({
  deviceId,
  path,
  depth,
  defaultOpen = false,
}: {
  deviceId: string;
  path: string;
  depth: number;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const { data, isLoading, error } = useQuery<DirEntryUsage[]>({
    queryKey: ["disk-tree", deviceId, path],
    queryFn: () => getDiskTree(deviceId, path),
    enabled: open,
    staleTime: 60_000,
  });

  const largest = data?.[0]?.size_bytes ?? 0;

  return (
    <div className={depth === 0 ? "mt-3" : "mt-1"}>
      {depth > 0 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <span className="inline-block w-3 text-center font-mono">
            {open ? "−" : "+"}
          </span>
        </button>
      )}
      {open && (
        <div className={depth > 0 ? "ml-4 border-l border-border pl-3" : ""}>
          {isLoading && (
            <p className="py-1 text-xs text-muted-foreground">
              Measuring… (du walks the whole subtree, so this can take a while)
            </p>
          )}
          {error && (
            <p className="py-1 text-xs text-destructive">
              {(error as Error).message}
            </p>
          )}
          {data?.length === 0 && (
            <p className="py-1 text-xs text-muted-foreground">Empty.</p>
          )}
          {data?.map((entry) => (
            <DirRow
              key={entry.path}
              deviceId={deviceId}
              entry={entry}
              depth={depth}
              largest={largest}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DirRow({
  deviceId,
  entry,
  depth,
  largest,
}: {
  deviceId: string;
  entry: DirEntryUsage;
  depth: number;
  largest: number;
}) {
  const [open, setOpen] = useState(false);
  const share = largest > 0 ? (entry.size_bytes / largest) * 100 : 0;

  return (
    <div>
      <div className="group flex items-center gap-2 py-0.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="inline-flex size-4 shrink-0 items-center justify-center rounded border border-border font-mono text-[10px] leading-none text-muted-foreground hover:bg-accent"
        >
          {open ? "−" : "+"}
        </button>
        <span className="w-24 shrink-0 text-right font-mono text-xs tabular-nums">
          {formatBytes(entry.size_bytes)}
        </span>
        {/* A bar relative to the biggest sibling, so the one directory that
            actually ate the disk is obvious without reading the numbers. */}
        <span className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-muted">
          <span
            className="block h-full rounded-full bg-primary/60"
            style={{ width: `${share}%` }}
          />
        </span>
        <span className="truncate font-mono text-xs" title={entry.path}>
          {entry.name}
        </span>
      </div>
      {open && (
        <div className="ml-6 border-l border-border pl-3">
          <DirNode
            deviceId={deviceId}
            path={entry.path}
            depth={depth + 1}
            defaultOpen
          />
        </div>
      )}
    </div>
  );
}
