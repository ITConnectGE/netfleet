"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { RequestAccessButton } from "@/components/request-access-button";
import {
  fetchDirectory,
  listAccessRequests,
  type AccessRequestPublic,
  type AccessRequestStatus,
  type DirectoryReport,
} from "@/lib/access-requests";

const STATUS_FILTERS: { value: AccessRequestStatus | "all"; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "denied", label: "Denied" },
  { value: "cancelled", label: "Cancelled" },
  { value: "all", label: "All" },
];

export default function AccessRequestsPage() {
  const [statusFilter, setStatusFilter] = useState<AccessRequestStatus | "all">(
    "pending",
  );
  const { data: requests, isLoading } = useQuery<AccessRequestPublic[]>({
    queryKey: ["access-requests", statusFilter],
    queryFn: () =>
      listAccessRequests(statusFilter === "all" ? undefined : statusFilter),
  });

  const { data: directory } = useQuery<DirectoryReport>({
    queryKey: ["access-directory"],
    queryFn: fetchDirectory,
  });

  return (
    <div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Access requests</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Browse every tenant, site and device in your organisation. Open a
          request for anything you can&apos;t reach yet — an admin will decide.
        </p>
      </div>

      <section className="mt-8">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Requests</h2>
          <div className="inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`rounded px-3 py-1.5 font-medium transition ${
                  statusFilter === f.value
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        {isLoading && (
          <p className="mt-3 text-sm text-muted-foreground">Loading…</p>
        )}
        {requests && requests.length === 0 && !isLoading && (
          <p className="mt-3 rounded-md border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
            Nothing here.
          </p>
        )}
        {requests && requests.length > 0 && (
          <div className="mt-3 overflow-hidden rounded-lg border border-border bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Requester</th>
                  <th className="px-3 py-2 font-medium">Target</th>
                  <th className="px-3 py-2 font-medium">Reason</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Created</th>
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {requests.map((r) => (
                  <tr key={r.id} className="align-top hover:bg-accent/30">
                    <td className="px-3 py-2">
                      <div className="font-medium">
                        {r.requester_display_name ?? r.requester_email}
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {r.requester_email}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <span className="font-mono">{r.scope_type}</span>
                      {r.scope_label && (
                        <span className="ml-1">· {r.scope_label}</span>
                      )}
                    </td>
                    <td className="max-w-xs truncate px-3 py-2 text-xs text-muted-foreground">
                      {r.reason ?? "—"}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-muted-foreground">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right text-xs">
                      <Link
                        href={`/dashboard/access-requests/${r.id}`}
                        className="text-primary hover:underline"
                      >
                        Open →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <DirectorySection directory={directory} />
    </div>
  );
}

function StatusBadge({ status }: { status: AccessRequestStatus }) {
  const cls = {
    pending: "bg-amber-100 text-amber-900",
    approved: "bg-emerald-100 text-emerald-900",
    denied: "bg-red-100 text-red-900",
    cancelled: "bg-zinc-100 text-zinc-800",
  }[status];
  return (
    <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {status}
    </span>
  );
}

function DirectorySection({ directory }: { directory: DirectoryReport | undefined }) {
  const [filter, setFilter] = useState("");
  const [onlyUnreachable, setOnlyUnreachable] = useState(false);

  const filteredTenants = useMemo(() => {
    if (!directory) return [];
    const needle = filter.trim().toLowerCase();
    return directory.tenants
      .map((t) => {
        const sites = t.sites
          .map((s) => {
            const devices = s.devices.filter((d) => {
              if (onlyUnreachable && d.has_access) return false;
              if (!needle) return true;
              return (
                d.name.toLowerCase().includes(needle) ||
                s.name.toLowerCase().includes(needle) ||
                t.name.toLowerCase().includes(needle)
              );
            });
            const sMatches =
              !needle ||
              s.name.toLowerCase().includes(needle) ||
              t.name.toLowerCase().includes(needle);
            if (onlyUnreachable && s.has_access && devices.length === 0)
              return null;
            if (!sMatches && devices.length === 0) return null;
            return { ...s, devices };
          })
          .filter((s): s is NonNullable<typeof s> => s !== null);
        const tMatches = !needle || t.name.toLowerCase().includes(needle);
        if (onlyUnreachable && t.has_access && sites.length === 0) return null;
        if (!tMatches && sites.length === 0) return null;
        return { ...t, sites };
      })
      .filter((t): t is NonNullable<typeof t> => t !== null);
  }, [directory, filter, onlyUnreachable]);

  return (
    <section className="mt-12">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold">Directory</h2>
          <p className="text-xs text-muted-foreground">
            Everything in your org. A red badge means you don&apos;t currently
            have access — request it.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs">
            <input
              type="checkbox"
              checked={onlyUnreachable}
              onChange={(e) => setOnlyUnreachable(e.target.checked)}
              className="size-3"
            />
            Show only what I can&apos;t reach
          </label>
          <input
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter…"
            className="rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </div>

      <div className="mt-3 space-y-3">
        {filteredTenants.length === 0 ? (
          <p className="rounded-md border border-dashed border-border bg-card p-6 text-center text-xs text-muted-foreground">
            Nothing matches.
          </p>
        ) : (
          filteredTenants.map((t) => (
            <div
              key={t.id}
              className="rounded-lg border border-border bg-card p-3"
            >
              <div className="flex items-baseline justify-between gap-2">
                <div className="font-semibold">{t.name}</div>
                <DirectoryActions
                  scopeType="tenant"
                  scopeId={t.id}
                  scopeLabel={t.name}
                  hasAccess={t.has_access}
                />
              </div>
              {t.sites.length > 0 && (
                <ul className="mt-2 space-y-1 border-l border-border pl-3">
                  {t.sites.map((s) => (
                    <li key={s.id}>
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-sm">{s.name}</span>
                        <DirectoryActions
                          scopeType="site"
                          scopeId={s.id}
                          scopeLabel={s.name}
                          hasAccess={s.has_access}
                        />
                      </div>
                      {s.devices.length > 0 && (
                        <ul className="mt-1 space-y-0.5 border-l border-border pl-3">
                          {s.devices.map((d) => (
                            <li
                              key={d.id}
                              className="flex items-baseline justify-between gap-2"
                            >
                              <span className="font-mono text-xs">{d.name}</span>
                              <DirectoryActions
                                scopeType="device"
                                scopeId={d.id}
                                scopeLabel={d.name}
                                hasAccess={d.has_access}
                              />
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function DirectoryActions({
  scopeType,
  scopeId,
  scopeLabel,
  hasAccess,
}: {
  scopeType: "tenant" | "site" | "device";
  scopeId: string;
  scopeLabel: string;
  hasAccess: boolean;
}) {
  if (hasAccess) {
    return (
      <span className="text-[10px] uppercase tracking-wide text-emerald-700">
        accessible
      </span>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] uppercase tracking-wide text-red-700">
        no access
      </span>
      <RequestAccessButton
        scopeType={scopeType}
        scopeId={scopeId}
        scopeLabel={scopeLabel}
      />
    </div>
  );
}
