"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { useToast } from "@/components/toast";
import { VendorIcon, distroLabel } from "@/components/vendor-icon";
import { api } from "@/lib/api";
import { listDevices, type Device } from "@/lib/devices";
import { listSites, type Site } from "@/lib/sites";
import { formatRelative } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * One screen for the whole Linux fleet.
 *
 * The counts come from the cached columns on `devices`, refreshed nightly
 * and whenever someone opens a host's Packages tab. Reading them live
 * would be one SSH session per row on every page load.
 */
export default function ServersPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [query, setQuery] = useState("");

  const { data: devices, isLoading } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: () => listSites(),
  });

  const refreshAll = useMutation({
    mutationFn: () =>
      api
        .post("devices/packages/refresh-all", { timeout: 600_000 })
        .json<{ checked: number; failed: number }>(),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      toast.success(
        "Fleet checked",
        `${r.checked} host(s) refreshed${r.failed ? `, ${r.failed} failed` : ""}.`,
      );
    },
    onError: (e: Error) => toast.error("Could not check the fleet", e.message),
  });

  const siteName = useMemo(
    () => new Map((sites ?? []).map((s) => [s.id, s.name])),
    [sites],
  );

  const servers = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (devices ?? [])
      .filter((d) => d.device_class === "server")
      .filter(
        (d) =>
          !needle ||
          [d.name, d.host, d.os_version, d.os_family]
            .filter(Boolean)
            .join(" ")
            .toLowerCase()
            .includes(needle),
      )
      // Most in need of attention first: security updates, then total,
      // then name. A fleet page that sorts alphabetically buries the one
      // box that matters.
      .sort(
        (a, b) =>
          (b.packages_security_count ?? -1) - (a.packages_security_count ?? -1) ||
          (b.packages_updates_count ?? -1) - (a.packages_updates_count ?? -1) ||
          a.name.localeCompare(b.name),
      );
  }, [devices, query]);

  const totals = useMemo(
    () => ({
      hosts: servers.length,
      updates: servers.reduce((n, d) => n + (d.packages_updates_count ?? 0), 0),
      security: servers.reduce((n, d) => n + (d.packages_security_count ?? 0), 0),
      reboots: servers.filter((d) => d.packages_reboot_required).length,
      unchecked: servers.filter((d) => !d.packages_checked_at).length,
    }),
    [servers],
  );

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Servers</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every Linux host in the fleet, with what each one is waiting to
            install.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refreshAll.mutate()}
          disabled={refreshAll.isPending}
          title="Re-read pending updates on every server. Takes a while on a large fleet."
          className="shrink-0 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          {refreshAll.isPending ? "Checking…" : "Check all now"}
        </button>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-4">
        <Stat label="Servers" value={totals.hosts} />
        <Stat label="Updates pending" value={totals.updates} />
        <Stat
          label="Security updates"
          value={totals.security}
          tone={totals.security > 0 ? "warn" : undefined}
        />
        <Stat
          label="Awaiting reboot"
          value={totals.reboots}
          tone={totals.reboots > 0 ? "warn" : undefined}
        />
      </div>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search name, IP or distribution…"
        className="mt-5 w-full max-w-sm rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />

      <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/80 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 font-medium">Server</th>
              <th className="px-3 py-2.5 font-medium">IP</th>
              <th className="px-3 py-2.5 font-medium">Distribution</th>
              <th className="px-3 py-2.5 font-medium">Kernel</th>
              <th className="px-3 py-2.5 text-right font-medium">Updates</th>
              <th className="px-3 py-2.5 text-right font-medium">Security</th>
              <th className="px-3 py-2.5 font-medium">Checked</th>
              <th className="px-3 py-2.5 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && servers.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">
                  {devices?.length
                    ? "No Linux servers yet — add one from Fleet → New device."
                    : "No devices yet."}
                </td>
              </tr>
            )}
            {servers.map((d) => (
              <tr key={d.id} className="hover:bg-accent/30">
                <td className="whitespace-nowrap px-3 py-2 align-top">
                  <Link
                    href={`/dashboard/devices/${d.id}`}
                    className="inline-flex items-center gap-2 font-medium hover:underline"
                  >
                    <VendorIcon
                      vendor={d.vendor}
                      deviceClass={d.device_class}
                      osFamily={d.os_family}
                      osVersion={d.os_version}
                      className="size-4 shrink-0 text-muted-foreground"
                    />
                    {d.name}
                  </Link>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">
                    {siteName.get(d.site_id) ?? ""}
                  </span>
                </td>
                <td className="whitespace-nowrap px-3 py-2 align-top font-mono text-xs">
                  {d.host}
                  <span className="text-muted-foreground">:{d.ssh_port}</span>
                </td>
                <td className="whitespace-nowrap px-3 py-2 align-top text-xs">
                  {d.os_version ?? (
                    <span className="text-muted-foreground/60">
                      {distroLabel(d.os_family, d.os_version)}
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2 align-top font-mono text-[11px] text-muted-foreground">
                  {d.firmware ?? "—"}
                </td>
                <td className="px-3 py-2 text-right align-top">
                  <Count
                    value={d.packages_updates_count}
                    href={`/dashboard/devices/${d.id}/packages`}
                  />
                </td>
                <td className="px-3 py-2 text-right align-top">
                  <Count
                    value={d.packages_security_count}
                    href={`/dashboard/devices/${d.id}/packages`}
                    tone={
                      (d.packages_security_count ?? 0) > 0 ? "warn" : undefined
                    }
                  />
                </td>
                <td className="whitespace-nowrap px-3 py-2 align-top text-[11px] text-muted-foreground">
                  {d.packages_check_error ? (
                    <span
                      className="text-destructive"
                      title={d.packages_check_error}
                    >
                      check failed
                    </span>
                  ) : d.packages_checked_at ? (
                    formatRelative(d.packages_checked_at)
                  ) : (
                    "never"
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-2 align-top">
                  <div className="flex flex-col items-start gap-1">
                    <StatusPill
                      status={d.status}
                      lastSeenAt={d.last_seen_at}
                      error={d.status_error}
                    />
                    {d.packages_reboot_required && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                        reboot required
                      </span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totals.unchecked > 0 && servers.length > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">
          {totals.unchecked} server(s) have never been checked. They are counted
          as zero above — use “Check all now”, or open a host&apos;s Packages
          tab.
        </p>
      )}
    </div>
  );
}

function Count({
  value,
  href,
  tone,
}: {
  value: number | null | undefined;
  href: string;
  tone?: "warn";
}) {
  // Null is "never checked", which is not the same as zero and must not
  // look like a clean bill of health.
  if (value == null) {
    return <span className="text-xs text-muted-foreground/50">—</span>;
  }
  return (
    <Link
      href={href}
      className={cn(
        "inline-block min-w-7 rounded px-1.5 py-0.5 text-center font-mono text-xs tabular-nums hover:underline",
        value === 0
          ? "text-muted-foreground"
          : tone === "warn"
            ? "bg-amber-100 font-semibold text-amber-900"
            : "bg-muted font-medium",
      )}
    >
      {value}
    </Link>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "warn";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        tone === "warn" ? "border-amber-300 bg-amber-50/50" : "border-border bg-card",
      )}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
