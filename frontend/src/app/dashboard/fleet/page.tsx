"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { listDevices, type Device } from "@/lib/devices";
import { listSites, type Site } from "@/lib/sites";
import { listTenants, type Tenant } from "@/lib/tenants";

type TenantNode = Tenant & {
  sites: SiteNode[];
  device_count: number;
  online_count: number;
  offline_count: number;
};

type SiteNode = Site & {
  devices: Device[];
  online_count: number;
  offline_count: number;
};

export default function FleetTreePage() {
  const { data: tenants } = useQuery<Tenant[]>({
    queryKey: ["tenants"],
    queryFn: listTenants,
  });
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: () => listSites(),
  });
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });

  const tree = useMemo<TenantNode[]>(() => {
    if (!tenants || !sites || !devices) return [];
    const devicesBySite = new Map<string, Device[]>();
    for (const d of devices) {
      const list = devicesBySite.get(d.site_id) ?? [];
      list.push(d);
      devicesBySite.set(d.site_id, list);
    }
    const sitesByTenant = new Map<string, SiteNode[]>();
    for (const s of sites) {
      const siteDevices = devicesBySite.get(s.id) ?? [];
      const node: SiteNode = {
        ...s,
        devices: siteDevices,
        online_count: siteDevices.filter((d) => d.status === "online").length,
        offline_count: siteDevices.filter(
          (d) => d.status === "offline" || d.status === "error",
        ).length,
      };
      const list = sitesByTenant.get(s.tenant_id) ?? [];
      list.push(node);
      sitesByTenant.set(s.tenant_id, list);
    }
    return tenants
      .map<TenantNode>((t) => {
        const tenantSites = sitesByTenant.get(t.id) ?? [];
        const device_count = tenantSites.reduce(
          (a, s) => a + s.devices.length,
          0,
        );
        const online_count = tenantSites.reduce(
          (a, s) => a + s.online_count,
          0,
        );
        const offline_count = tenantSites.reduce(
          (a, s) => a + s.offline_count,
          0,
        );
        return {
          ...t,
          sites: tenantSites.sort((a, b) => a.name.localeCompare(b.name)),
          device_count,
          online_count,
          offline_count,
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [tenants, sites, devices]);

  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // When a filter is active, auto-expand everything matching so the
  // operator sees the hits without manually toggling each node.
  const filtered = useMemo(() => {
    if (!filter.trim()) return tree;
    const needle = filter.toLowerCase();
    return tree
      .map<TenantNode | null>((t) => {
        const sitesMatched = t.sites
          .map<SiteNode | null>((s) => {
            const siteMatch =
              s.name.toLowerCase().includes(needle) ||
              (s.address?.toLowerCase().includes(needle) ?? false);
            const deviceHits = s.devices.filter(
              (d) =>
                d.name.toLowerCase().includes(needle) ||
                d.host.toLowerCase().includes(needle) ||
                (d.model?.toLowerCase().includes(needle) ?? false),
            );
            if (siteMatch) return s; // keep full device list
            if (deviceHits.length > 0) return { ...s, devices: deviceHits };
            return null;
          })
          .filter((x): x is SiteNode => x !== null);
        const tenantMatch = t.name.toLowerCase().includes(needle);
        if (tenantMatch) return t;
        if (sitesMatched.length > 0) return { ...t, sites: sitesMatched };
        return null;
      })
      .filter((x): x is TenantNode => x !== null);
  }, [tree, filter]);

  const allExpanded =
    expanded.size === filtered.reduce((a, t) => a + 1 + t.sites.length, 0) &&
    filtered.length > 0;
  function expandAll() {
    const ids = new Set<string>();
    for (const t of filtered) {
      ids.add(`t:${t.id}`);
      for (const s of t.sites) ids.add(`s:${s.id}`);
    }
    setExpanded(ids);
  }
  function collapseAll() {
    setExpanded(new Set());
  }

  const isOpen = (key: string) => expanded.has(key) || filter.trim().length > 0;
  const toggle = (key: string) => {
    if (filter.trim()) return; // ignore individual toggles while filtering
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Fleet tree</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            One page, everything: each tenant, the sites under them, and the
            devices at each site. Click a node to expand. Use the filter to
            jump to a name, host or address anywhere in the tree.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={allExpanded ? collapseAll : expandAll}
            disabled={filtered.length === 0}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
          >
            {allExpanded ? "Collapse all" : "Expand all"}
          </button>
        </div>
      </div>

      <input
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="filter tenants, sites, devices by name / host / address…"
        className="mt-4 block w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />

      {filtered.length === 0 ? (
        <div className="mt-6 rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
          {filter ? "Nothing matches that filter." : "No tenants yet."}
        </div>
      ) : (
        <ul className="mt-6 space-y-1.5">
          {filtered.map((t) => (
            <TenantRow
              key={t.id}
              tenant={t}
              isOpen={isOpen(`t:${t.id}`)}
              onToggle={() => toggle(`t:${t.id}`)}
              isOpenSite={(sid) => isOpen(`s:${sid}`)}
              onToggleSite={(sid) => toggle(`s:${sid}`)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function TenantRow({
  tenant,
  isOpen,
  onToggle,
  isOpenSite,
  onToggleSite,
}: {
  tenant: TenantNode;
  isOpen: boolean;
  onToggle: () => void;
  isOpenSite: (siteId: string) => boolean;
  onToggleSite: (siteId: string) => void;
}) {
  return (
    <li className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <button
          type="button"
          onClick={onToggle}
          className="flex min-w-0 items-center gap-2 text-left"
        >
          <Chevron open={isOpen} />
          <span className="font-semibold">{tenant.name}</span>
          <span className="text-xs text-muted-foreground">
            {tenant.sites.length} site{tenant.sites.length === 1 ? "" : "s"} ·{" "}
            {tenant.device_count} device{tenant.device_count === 1 ? "" : "s"}
          </span>
        </button>
        <div className="flex shrink-0 items-center gap-1.5">
          <Counter color="emerald" value={tenant.online_count} title="online" />
          <Counter color="red" value={tenant.offline_count} title="offline" />
          <Link
            href={`/dashboard/tenants/${tenant.id}`}
            className="ml-2 text-[11px] text-primary hover:underline"
          >
            open →
          </Link>
        </div>
      </div>

      {isOpen && (
        <ul className="border-t border-border bg-background/40 p-2 pl-6">
          {tenant.sites.length === 0 && (
            <li className="px-3 py-2 text-xs text-muted-foreground">
              No sites yet.{" "}
              <Link
                href={`/dashboard/tenants/${tenant.id}`}
                className="text-primary hover:underline"
              >
                Add one →
              </Link>
            </li>
          )}
          {tenant.sites.map((s) => (
            <SiteRow
              key={s.id}
              site={s}
              isOpen={isOpenSite(s.id)}
              onToggle={() => onToggleSite(s.id)}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function SiteRow({
  site,
  isOpen,
  onToggle,
}: {
  site: SiteNode;
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <li className="rounded-md">
      <div className="flex items-center justify-between gap-2 px-3 py-1.5 hover:bg-accent/30">
        <button
          type="button"
          onClick={onToggle}
          className="flex min-w-0 items-center gap-2 text-left"
        >
          <Chevron open={isOpen} />
          <span className="font-medium">{site.name}</span>
          {site.address && (
            <span className="truncate text-[11px] text-muted-foreground">
              · {site.address}
            </span>
          )}
          <span className="text-[11px] text-muted-foreground">
            · {site.devices.length} device{site.devices.length === 1 ? "" : "s"}
          </span>
        </button>
        <div className="flex shrink-0 items-center gap-1.5">
          <Counter color="emerald" value={site.online_count} title="online" />
          <Counter color="red" value={site.offline_count} title="offline" />
          <Link
            href={`/dashboard/sites/${site.id}`}
            className="ml-2 text-[11px] text-primary hover:underline"
          >
            open →
          </Link>
        </div>
      </div>

      {isOpen && (
        <ul className="ml-6 border-l border-border pl-3">
          {site.devices.length === 0 && (
            <li className="py-1.5 text-xs text-muted-foreground">
              No devices.{" "}
              <Link
                href="/dashboard/devices"
                className="text-primary hover:underline"
              >
                Add one →
              </Link>
            </li>
          )}
          {site.devices.map((d) => (
            <DeviceRow key={d.id} device={d} />
          ))}
        </ul>
      )}
    </li>
  );
}

function normFw(v: string | null | undefined): string {
  if (!v) return "";
  return v.replace(/\s*\([^)]*\)\s*$/, "").trim();
}

function DeviceRow({ device }: { device: Device }) {
  const fwUpgrade =
    device.firmware_available &&
    device.firmware &&
    normFw(device.firmware_available) !== normFw(device.firmware);
  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-2 py-1 text-sm">
      <Link
        href={`/dashboard/devices/${device.id}`}
        className="flex min-w-0 items-center gap-2 hover:underline"
      >
        <span className="truncate font-medium">{device.name}</span>
        <span className="truncate font-mono text-[10px] text-muted-foreground">
          {device.vendor} · {device.host}:{device.port}
        </span>
        {fwUpgrade && (
          <span
            className="rounded-md bg-amber-100 px-1 py-0.5 text-[9px] font-medium text-amber-900"
            title={`Update available: ${device.firmware_available}`}
          >
            fw ↑
          </span>
        )}
      </Link>
      <StatusPill status={device.status} />
    </li>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      className={`size-3.5 shrink-0 text-muted-foreground transition-transform ${
        open ? "rotate-90" : ""
      }`}
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function Counter({
  color,
  value,
  title,
}: {
  color: "emerald" | "red";
  value: number;
  title: string;
}) {
  if (value === 0) return null;
  const cls =
    color === "emerald"
      ? "bg-emerald-100 text-emerald-800"
      : "bg-red-100 text-red-800";
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium ${cls}`}
      title={title}
    >
      {value} {title}
    </span>
  );
}
