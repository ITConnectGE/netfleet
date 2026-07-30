"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { VendorIcon } from "@/components/vendor-icon";
import { listDevices, type Device } from "@/lib/devices";
import { listSites, type Site } from "@/lib/sites";
import { listTenants, type Tenant } from "@/lib/tenants";

function normFw(v: string | null | undefined): string {
  if (!v) return "";
  return v.replace(/\s*\([^)]*\)\s*$/, "").trim();
}

type Row = {
  key: string;
  tenant: Tenant;
  site: Site | null;
  device: Device | null;
  tenantFirst: boolean;
  siteFirst: boolean;
};

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

  const rows = useMemo<Row[]>(() => {
    if (!tenants || !sites || !devices) return [];
    const devicesBySite = new Map<string, Device[]>();
    for (const d of devices) {
      const list = devicesBySite.get(d.site_id) ?? [];
      list.push(d);
      devicesBySite.set(d.site_id, list);
    }
    const sitesByTenant = new Map<string, Site[]>();
    for (const s of sites) {
      const list = sitesByTenant.get(s.tenant_id) ?? [];
      list.push(s);
      sitesByTenant.set(s.tenant_id, list);
    }
    const out: Row[] = [];
    const sortedTenants = [...tenants].sort((a, b) =>
      a.name.localeCompare(b.name),
    );
    for (const t of sortedTenants) {
      const tSites = (sitesByTenant.get(t.id) ?? []).sort((a, b) =>
        a.name.localeCompare(b.name),
      );
      let tenantFirstUsed = false;
      if (tSites.length === 0) {
        out.push({
          key: `t:${t.id}`,
          tenant: t,
          site: null,
          device: null,
          tenantFirst: true,
          siteFirst: false,
        });
        continue;
      }
      for (const s of tSites) {
        const sDevices = (devicesBySite.get(s.id) ?? []).sort((a, b) =>
          a.name.localeCompare(b.name),
        );
        let siteFirstUsed = false;
        if (sDevices.length === 0) {
          out.push({
            key: `s:${s.id}`,
            tenant: t,
            site: s,
            device: null,
            tenantFirst: !tenantFirstUsed,
            siteFirst: true,
          });
          tenantFirstUsed = true;
          continue;
        }
        for (const d of sDevices) {
          out.push({
            key: `d:${d.id}`,
            tenant: t,
            site: s,
            device: d,
            tenantFirst: !tenantFirstUsed,
            siteFirst: !siteFirstUsed,
          });
          tenantFirstUsed = true;
          siteFirstUsed = true;
        }
      }
    }
    return out;
  }, [tenants, sites, devices]);

  const [filter, setFilter] = useState("");

  const filtered = useMemo<Row[]>(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return rows;
    const hits = rows.filter((r) => {
      const haystack = [
        r.tenant.name,
        r.site?.name,
        r.site?.address,
        r.device?.name,
        r.device?.host,
        r.device?.model,
        r.device?.firmware,
        r.device?.vendor,
        r.device?.os_version,
        r.device?.os_family,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
    // Recompute tenant/site "first" flags within the filtered subset so
    // group cells still de-dup correctly after rows fall away.
    let lastTenant = "";
    let lastSite = "";
    return hits.map((r) => {
      const tFirst = r.tenant.id !== lastTenant;
      const sFirst = (r.site?.id ?? "") !== lastSite || tFirst;
      lastTenant = r.tenant.id;
      lastSite = r.site?.id ?? "";
      return { ...r, tenantFirst: tFirst, siteFirst: sFirst };
    });
  }, [rows, filter]);

  const totalTenants = useMemo(
    () => new Set(filtered.map((r) => r.tenant.id)).size,
    [filtered],
  );
  const totalSites = useMemo(
    () =>
      new Set(filtered.filter((r) => r.site).map((r) => r.site!.id)).size,
    [filtered],
  );
  const totalDevices = useMemo(
    () => filtered.filter((r) => r.device).length,
    [filtered],
  );

  return (
    <div>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Fleet</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every tenant, site and device in one table. Click any name to open
            its detail page.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-xs text-muted-foreground">
            {totalTenants} tenant{totalTenants === 1 ? "" : "s"} · {totalSites}{" "}
            site{totalSites === 1 ? "" : "s"} · {totalDevices} device
            {totalDevices === 1 ? "" : "s"}
          </div>
          <Link
            href="/dashboard/wg-s2s/new"
            className="rounded-md border border-primary/40 bg-primary/5 px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/10"
            title="Build a site-to-site WireGuard tunnel between two MikroTik routers"
          >
            🔗 S2S WG
          </Link>
          <Link
            href="/dashboard/fleet/new"
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90"
          >
            + Add
          </Link>
        </div>
      </div>

      <label htmlFor="fleet-search" className="sr-only">
        Filter fleet by tenant, site, device, host or model
      </label>
      <input
        id="fleet-search"
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search tenant / site / device / host / model…"
        className="mt-4 block w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />

      {filtered.length === 0 ? (
        <EmptyFleetState hasFilter={Boolean(filter)} />
      ) : (
        <div className="relative mt-4 overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-muted/80 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr className="border-b border-border">
                <th scope="col" className="px-3 py-2.5 font-medium">Tenant</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Site</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Device</th>
                <th scope="col" className="px-3 py-2.5 font-medium">IP / Host</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Model / OS</th>
                <th scope="col" className="px-3 py-2.5 font-medium">
                  Firmware / Kernel
                </th>
                <th scope="col" className="px-3 py-2.5 font-medium">Status</th>
                <th scope="col" className="px-3 py-2.5 font-medium text-right">Details</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <FleetRow key={r.key} row={r} highlight={filter.toLowerCase()} />
              ))}
            </tbody>
          </table>
          {/* Right-edge fade hint that the table scrolls horizontally on
              narrow viewports. pointer-events-none so it doesn't intercept
              clicks on the rightmost column. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute right-0 top-0 hidden h-full w-8 bg-gradient-to-l from-card to-transparent md:max-lg:block"
          />
        </div>
      )}
    </div>
  );
}

function EmptyFleetState({ hasFilter }: { hasFilter: boolean }) {
  if (hasFilter) {
    return (
      <div className="mt-6 rounded-lg border-2 border-dashed border-border/60 bg-card/50 p-10 text-center">
        <p className="text-sm font-medium text-foreground">
          Nothing matches that filter.
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Try a shorter term, or clear the search box.
        </p>
      </div>
    );
  }
  return (
    <div className="mt-6 rounded-lg border-2 border-dashed border-border/60 bg-card/50 p-10 text-center">
      <p className="text-base font-medium text-foreground">No tenants yet</p>
      <p className="mt-1 text-sm text-muted-foreground">
        Create your first tenant, then add sites and devices under it.
      </p>
      <Link
        href="/dashboard/fleet/new"
        className="mt-4 inline-flex items-center rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
      >
        + Add tenant
      </Link>
    </div>
  );
}

function FleetRow({ row, highlight }: { row: Row; highlight: string }) {
  const { tenant, site, device, tenantFirst, siteFirst } = row;
  const fwUpgrade =
    device?.firmware_available &&
    device?.firmware &&
    normFw(device.firmware_available) !== normFw(device.firmware);
  // Tenant boundary now gets a subtle background tint in addition to the
  // heavier top border — background change is far more scannable than a
  // 2px line. Site rows inside a tenant keep a thin divider.
  const groupBorder = tenantFirst
    ? "border-t-2 border-border bg-muted/30"
    : siteFirst
      ? "border-t border-border/60"
      : "";
  return (
    <tr className={`${groupBorder} transition-colors hover:bg-accent/40`}>
      <td className="whitespace-nowrap px-3 py-2 align-top">
        {tenantFirst ? (
          <Link
            href={`/dashboard/tenants/${tenant.id}`}
            className="font-semibold text-foreground hover:underline"
          >
            <Highlighted text={tenant.name} needle={highlight} />
          </Link>
        ) : (
          <span className="select-none text-muted-foreground/30">·</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top">
        {site == null ? (
          <span className="text-xs italic text-muted-foreground">
            No sites
          </span>
        ) : siteFirst ? (
          <Link
            href={`/dashboard/sites/${site.id}`}
            className="text-foreground/90 hover:underline"
          >
            <Highlighted text={site.name} needle={highlight} />
          </Link>
        ) : (
          <span className="select-none text-muted-foreground/30">·</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top">
        {device == null ? (
          site == null ? null : (
            <span className="text-xs italic text-muted-foreground">
              No devices
            </span>
          )
        ) : (
          <Link
            href={`/dashboard/devices/${device.id}`}
            className="inline-flex items-center gap-2 font-medium text-foreground hover:underline"
          >
            <VendorIcon
              vendor={device.vendor}
              deviceClass={device.device_class}
              osFamily={device.os_family}
              osVersion={device.os_version}
              className="size-4 shrink-0 text-muted-foreground"
            />
            <Highlighted text={device.name} needle={highlight} />
          </Link>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top font-mono text-xs">
        {device ? (
          <span className="text-foreground">
            <Highlighted text={device.host} needle={highlight} />
            <span className="text-muted-foreground">
              {/* Servers are reached over SSH; `port` is the RouterOS API
                  port and means nothing for them. */}
              :{device.device_class === "server" ? device.ssh_port : device.port}
            </span>
          </span>
        ) : (
          <span className="text-muted-foreground/40">—</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top text-xs text-muted-foreground">
        {/* One column, two meanings: hardware model for network gear, the
            distro for a server. They answer the same question — "what is
            this thing?" — so they share a column rather than each having
            one that is empty for half the fleet. */}
        {device?.device_class === "server" ? (
          device.os_version ? (
            <Highlighted text={device.os_version} needle={highlight} />
          ) : (
            <span className="text-muted-foreground/40">
              {device.status === "unknown" ? "not yet detected" : "—"}
            </span>
          )
        ) : device?.model ? (
          <Highlighted text={device.model} needle={highlight} />
        ) : (
          <span className="text-muted-foreground/40">—</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top text-xs text-muted-foreground">
        {device?.firmware ? (
          <span className="inline-flex items-baseline gap-1.5">
            <Highlighted text={device.firmware} needle={highlight} />
            {/* `firmware` holds the kernel release on a server. The upgrade
                badge is RouterOS-only — a pending kernel is a package
                update, which is a different mechanism entirely. */}
            {fwUpgrade && device.device_class !== "server" && (
              <span
                className="rounded-md bg-amber-100 px-1.5 py-0.5 font-mono text-[10px] font-medium text-amber-900"
                title={`Update available: ${device.firmware_available}`}
                aria-label={`Update available to ${device.firmware_available}`}
              >
                ↑ {device.firmware_available}
              </span>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground/40">—</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top">
        {device ? (
          <StatusPill
            status={device.status}
            lastSeenAt={device.last_seen_at}
            error={device.status_error}
          />
        ) : null}
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top text-right">
        {device ? (
          <Link
            href={`/dashboard/devices/${device.id}`}
            className="text-xs font-medium text-primary hover:underline"
          >
            Open →
          </Link>
        ) : site ? (
          <Link
            href={`/dashboard/sites/${site.id}`}
            className="text-xs text-primary hover:underline"
          >
            Open site →
          </Link>
        ) : (
          <Link
            href={`/dashboard/tenants/${tenant.id}`}
            className="text-xs text-primary hover:underline"
          >
            Open tenant →
          </Link>
        )}
      </td>
    </tr>
  );
}

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
