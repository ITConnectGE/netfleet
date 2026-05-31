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

function normFw(v: string | null | undefined): string {
  if (!v) return "";
  return v.replace(/\s*\([^)]*\)\s*$/, "").trim();
}

export default function FleetPage() {
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
      const siteDevices = (devicesBySite.get(s.id) ?? []).sort((a, b) =>
        a.name.localeCompare(b.name),
      );
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
        const tenantSites = (sitesByTenant.get(t.id) ?? []).sort((a, b) =>
          a.name.localeCompare(b.name),
        );
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
          sites: tenantSites,
          device_count,
          online_count,
          offline_count,
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [tenants, sites, devices]);

  const [filter, setFilter] = useState("");

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
            if (siteMatch) return s;
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

  const totalDevices = filtered.reduce((a, t) => a + t.device_count, 0);
  const totalSites = filtered.reduce((a, t) => a + t.sites.length, 0);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Fleet</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every tenant, site and device on one page. Click any name to open
            its detail.
          </p>
        </div>
        <div className="text-xs text-muted-foreground">
          {filtered.length} tenant{filtered.length === 1 ? "" : "s"} ·{" "}
          {totalSites} site{totalSites === 1 ? "" : "s"} · {totalDevices} device
          {totalDevices === 1 ? "" : "s"}
        </div>
      </div>

      <input
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search tenant / site / device / host…"
        className="mt-4 block w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />

      {filtered.length === 0 ? (
        <div className="mt-6 rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
          {filter ? "Nothing matches that filter." : "No tenants yet."}
        </div>
      ) : (
        <div className="mt-6 space-y-10">
          {filtered.map((t) => (
            <TenantBlock key={t.id} tenant={t} highlight={filter.toLowerCase()} />
          ))}
        </div>
      )}
    </div>
  );
}

function TenantBlock({
  tenant,
  highlight,
}: {
  tenant: TenantNode;
  highlight: string;
}) {
  return (
    <section>
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border pb-2">
        <Link
          href={`/dashboard/tenants/${tenant.id}`}
          className="text-lg font-semibold tracking-tight hover:underline"
        >
          <Highlighted text={tenant.name} needle={highlight} />
        </Link>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>
            {tenant.sites.length} site{tenant.sites.length === 1 ? "" : "s"} ·{" "}
            {tenant.device_count} device{tenant.device_count === 1 ? "" : "s"}
          </span>
          <Counter color="emerald" value={tenant.online_count} title="online" />
          <Counter color="red" value={tenant.offline_count} title="offline" />
        </div>
      </div>

      {tenant.sites.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">
          No sites yet.{" "}
          <Link
            href={`/dashboard/tenants/${tenant.id}`}
            className="text-primary hover:underline"
          >
            Add one →
          </Link>
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          {tenant.sites.map((s) => (
            <SiteBlock key={s.id} site={s} highlight={highlight} />
          ))}
        </div>
      )}
    </section>
  );
}

function SiteBlock({ site, highlight }: { site: SiteNode; highlight: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="min-w-0">
          <Link
            href={`/dashboard/sites/${site.id}`}
            className="font-medium hover:underline"
          >
            <Highlighted text={site.name} needle={highlight} />
          </Link>
          {site.address && (
            <span className="ml-2 text-[11px] text-muted-foreground">
              · {site.address}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span>
            {site.devices.length} device{site.devices.length === 1 ? "" : "s"}
          </span>
          <Counter color="emerald" value={site.online_count} title="online" />
          <Counter color="red" value={site.offline_count} title="offline" />
        </div>
      </div>

      {site.devices.length === 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">No devices.</p>
      ) : (
        <ul className="mt-3 divide-y divide-border/60">
          {site.devices.map((d) => (
            <DeviceRow key={d.id} device={d} highlight={highlight} />
          ))}
        </ul>
      )}
    </div>
  );
}

function DeviceRow({
  device,
  highlight,
}: {
  device: Device;
  highlight: string;
}) {
  const fwUpgrade =
    device.firmware_available &&
    device.firmware &&
    normFw(device.firmware_available) !== normFw(device.firmware);
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-1.5 text-sm">
      <Link
        href={`/dashboard/devices/${device.id}`}
        className="flex min-w-0 flex-1 items-baseline gap-2 hover:underline"
      >
        <span className="truncate font-medium">
          <Highlighted text={device.name} needle={highlight} />
        </span>
        <span className="truncate font-mono text-[11px] text-muted-foreground">
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

// Wraps any occurrence of `needle` inside `text` in a <mark> so the
// matching characters stand out during a search.
function Highlighted({ text, needle }: { text: string; needle: string }) {
  if (!needle) return <>{text}</>;
  const idx = text.toLowerCase().indexOf(needle);
  if (idx < 0) return <>{text}</>;
  const before = text.slice(0, idx);
  const hit = text.slice(idx, idx + needle.length);
  const after = text.slice(idx + needle.length);
  return (
    <>
      {before}
      <mark className="rounded bg-amber-200/70 px-0.5 text-foreground">
        {hit}
      </mark>
      {after}
    </>
  );
}
