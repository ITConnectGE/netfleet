"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import {
  getPackages,
  listPackageRuns,
  refreshPackages,
  upgradePackages,
  type PackageRun,
  type PackageState,
} from "@/lib/packages";
import { cn } from "@/lib/utils";

export default function PackagesPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const toast = useToast();
  const [selected, setSelected] = useState<string[]>([]);
  const [filter, setFilter] = useState("");

  const { data, isLoading, error, refetch, isFetching } = useQuery<PackageState>({
    queryKey: ["packages", id],
    queryFn: () => getPackages(id),
    enabled: Boolean(id),
  });

  const { data: runs } = useQuery<PackageRun[]>({
    queryKey: ["package-runs", id],
    queryFn: () => listPackageRuns(id),
    enabled: Boolean(id),
    // While something is in flight, poll: an upgrade can take half an hour
    // and the only signal it finished is this row changing state.
    refetchInterval: (q) =>
      q.state.data?.some((r) => r.state === "running") ? 5_000 : false,
  });

  const active = runs?.find((r) => r.state === "running");

  const refresh = useMutation({
    mutationFn: () => refreshPackages(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["package-runs", id] });
      toast.success("Refresh started", "Reading the repositories.");
    },
    onError: (e: Error) => toast.error("Could not refresh", e.message),
  });

  const upgrade = useMutation({
    mutationFn: (pkgs: string[]) => upgradePackages(id, pkgs),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["package-runs", id] });
      setSelected([]);
      toast.success(
        "Upgrade started",
        "It runs in the background — you can leave this page.",
      );
    },
    onError: (e: Error) => toast.error("Could not start the upgrade", e.message),
  });

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (data?.updates ?? []).filter(
      (u) => !needle || u.name.toLowerCase().includes(needle),
    );
  }, [data, filter]);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Packages</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Pending updates from the host&apos;s own package manager
            {data?.manager ? ` (${data.manager})` : ""}. Upgrades run in the
            background and survive leaving this page.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            {isFetching ? "Reading…" : "Reload"}
          </button>
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={Boolean(active) || refresh.isPending}
            title="apt-get update — re-reads the repositories, changes nothing"
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
          >
            Refresh lists
          </button>
          <button
            type="button"
            onClick={() => {
              const n = selected.length || data?.updates.length || 0;
              if (
                !confirm(
                  selected.length
                    ? `Upgrade ${selected.length} selected package(s)?`
                    : `Upgrade all ${n} package(s) on this host?\n\nServices may restart. If the kernel is among them the host will need a reboot afterwards.`,
                )
              )
                return;
              upgrade.mutate(selected);
            }}
            disabled={
              Boolean(active) || upgrade.isPending || !data?.updates.length
            }
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {selected.length ? `Upgrade ${selected.length}` : "Upgrade all"}
          </button>
        </div>
      </div>

      {active && <RunBanner run={active} />}

      {data && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Updates pending" value={String(data.updates.length)} />
          <Stat
            label="Security updates"
            value={String(data.security_count)}
            tone={data.security_count > 0 ? "warn" : undefined}
          />
          <Stat
            label="Reboot required"
            value={data.reboot_required ? "Yes" : "No"}
            tone={data.reboot_required ? "warn" : undefined}
            detail={
              data.reboot_required_by.length
                ? data.reboot_required_by.join(", ")
                : undefined
            }
          />
        </div>
      )}

      {data?.last_refreshed_iso && (
        <p className="text-xs text-muted-foreground">
          Repository lists last refreshed: {data.last_refreshed_iso}
        </p>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Reading…</p>}
      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </p>
      )}

      {data && data.updates.length === 0 && (
        <p className="rounded-md border border-emerald-300 bg-emerald-50/60 px-3 py-2 text-sm text-emerald-900">
          Everything is up to date.
        </p>
      )}

      {data && data.updates.length > 0 && (
        <>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter packages…"
            className="w-64 rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/60 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="w-8 px-3 py-2" />
                  <th className="px-3 py-2 font-medium">Package</th>
                  <th className="px-3 py-2 font-medium">Installed</th>
                  <th className="px-3 py-2 font-medium">Available</th>
                  <th className="px-3 py-2 font-medium">Origin</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((u) => (
                  <tr key={u.name} className="hover:bg-accent/30">
                    <td className="px-3 py-1.5">
                      <input
                        type="checkbox"
                        checked={selected.includes(u.name)}
                        onChange={(e) =>
                          setSelected((prev) =>
                            e.target.checked
                              ? [...prev, u.name]
                              : prev.filter((x) => x !== u.name),
                          )
                        }
                        className="size-3.5 rounded"
                        aria-label={`Select ${u.name}`}
                      />
                    </td>
                    <td className="px-3 py-1.5 font-mono text-xs">
                      {u.name}
                      {u.is_security && (
                        <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                          security
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                      {u.current_version ?? "—"}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-[11px]">
                      {u.candidate_version ?? "—"}
                    </td>
                    <td className="px-3 py-1.5 text-[11px] text-muted-foreground">
                      {u.origin ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {runs && runs.length > 0 && <RunHistory runs={runs} />}
    </section>
  );
}

function RunBanner({ run }: { run: PackageRun }) {
  return (
    <div className="rounded-lg border border-sky-300 bg-sky-50/60 p-3 text-sm">
      <p className="font-medium text-sky-900">
        {run.kind === "upgrade" ? "Upgrade" : "Refresh"} in progress
      </p>
      <p className="mt-0.5 text-xs text-sky-900/80">
        Started {new Date(run.started_at).toLocaleTimeString()}. It runs on the
        host, so closing this page will not stop it.
      </p>
    </div>
  );
}

function RunHistory({ runs }: { runs: PackageRun[] }) {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div>
      <h3 className="text-sm font-semibold">Recent runs</h3>
      <div className="mt-2 space-y-1.5">
        {runs.map((r) => (
          <div key={r.id} className="rounded-md border border-border bg-card">
            <button
              type="button"
              onClick={() => setOpen(open === r.id ? null : r.id)}
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-xs hover:bg-accent/30"
            >
              <span className="flex items-center gap-2">
                <StateDot state={r.state} />
                <span className="font-medium">{r.kind}</span>
                {r.packages && (
                  <span className="font-mono text-muted-foreground">
                    {r.packages}
                  </span>
                )}
              </span>
              <span className="text-muted-foreground">
                {new Date(r.started_at).toLocaleString()}
                {r.finished_at &&
                  ` · ${Math.max(
                    1,
                    Math.round(
                      (new Date(r.finished_at).getTime() -
                        new Date(r.started_at).getTime()) /
                        1000,
                    ),
                  )}s`}
              </span>
            </button>
            {open === r.id && (
              <div className="border-t border-border px-3 py-2">
                {r.error && (
                  <p className="mb-2 rounded bg-destructive/10 px-2 py-1 text-xs text-destructive">
                    {r.error}
                  </p>
                )}
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-zinc-950 p-2 font-mono text-[11px] text-zinc-100">
                  {r.output || "(no output)"}
                </pre>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function StateDot({ state }: { state: PackageRun["state"] }) {
  const tone =
    state === "succeeded"
      ? "bg-emerald-500"
      : state === "running"
        ? "bg-sky-500 animate-pulse"
        : state === "interrupted"
          ? "bg-amber-500"
          : "bg-red-500";
  return (
    <span
      className={cn("inline-block size-2 shrink-0 rounded-full", tone)}
      title={state}
    />
  );
}

function Stat({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "warn";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        tone === "warn"
          ? "border-amber-300 bg-amber-50/50"
          : "border-border bg-card",
      )}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-xl font-semibold tabular-nums">{value}</p>
      {detail && (
        <p className="mt-0.5 break-words text-[11px] text-muted-foreground">
          {detail}
        </p>
      )}
    </div>
  );
}
