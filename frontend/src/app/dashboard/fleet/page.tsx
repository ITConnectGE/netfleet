"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusPill } from "@/components/status-pill";
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
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Fleet</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Every tenant, site and device in one table. Click any name to open
            its detail page.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-muted-foreground">
            {totalTenants} tenant{totalTenants === 1 ? "" : "s"} · {totalSites}{" "}
            site{totalSites === 1 ? "" : "s"} · {totalDevices} device
            {totalDevices === 1 ? "" : "s"}
          </div>
          <Link
            href="/dashboard/fleet/new"
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90"
          >
            + Add
          </Link>
        </div>
      </div>

      <input
        type="search"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Search tenant / site / device / host / model…"
        className="mt-4 block w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
      />

      {filtered.length === 0 ? (
        <div className="mt-6 rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
          {filter ? "Nothing matches that filter." : "No tenants yet."}
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Tenant</th>
                <th className="px-3 py-2 font-medium">Site</th>
                <th className="px-3 py-2 font-medium">Device</th>
                <th className="px-3 py-2 font-medium">IP / Host</th>
                <th className="px-3 py-2 font-medium">Model</th>
                <th className="px-3 py-2 font-medium">Firmware</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium text-right">Details</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <FleetRow key={r.key} row={r} highlight={filter.toLowerCase()} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FleetRow({ row, highlight }: { row: Row; highlight: string }) {
  const { tenant, site, device, tenantFirst, siteFirst } = row;
  const fwUpgrade =
    device?.firmware_available &&
    device?.firmware &&
    normFw(device.firmware_available) !== normFw(device.firmware);
  // Subtle top border at tenant boundaries so the eye can find group
  // breaks even when the tenant cell is blank on continuation rows.
  const groupBorder = tenantFirst ? "border-t border-border" : "";
  return (
    <tr className={`${groupBorder} hover:bg-muted/30`}>
      <td className="whitespace-nowrap px-3 py-1.5 align-top">
        {tenantFirst ? (
          <Link
            href={`/dashboard/tenants/${tenant.id}`}
            className="font-medium hover:underline"
          >
            <Highlighted text={tenant.name} needle={highlight} />
          </Link>
        ) : (
          <span className="text-muted-foreground/40">↳</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 align-top">
        {site == null ? (
          <span className="text-xs italic text-muted-foreground">
            No sites
          </span>
        ) : siteFirst ? (
          <Link
            href={`/dashboard/sites/${site.id}`}
            className="hover:underline"
          >
            <Highlighted text={site.name} needle={highlight} />
          </Link>
        ) : (
          <span className="text-muted-foreground/40">↳</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 align-top">
        {device == null ? (
          site == null ? null : (
            <span className="text-xs italic text-muted-foreground">
              No devices
            </span>
          )
        ) : (
          <Link
            href={`/dashboard/devices/${device.id}`}
            className="font-medium hover:underline"
          >
            <Highlighted text={device.name} needle={highlight} />
          </Link>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 align-top font-mono text-xs text-muted-foreground">
        {device ? (
          <Highlighted
            text={`${device.host}:${device.port}`}
            needle={highlight}
          />
        ) : (
          <span className="text-muted-foreground/40">—</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 align-top text-xs">
        {device?.model ? (
          <Highlighted text={device.model} needle={highlight} />
        ) : (
          <span className="text-muted-foreground/40">—</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 align-top text-xs">
        {device?.firmware ? (
          <span className="inline-flex items-baseline gap-1">
            <Highlighted text={device.firmware} needle={highlight} />
            {fwUpgrade && (
              <span
                className="rounded-md bg-amber-100 px-1 py-0.5 text-[9px] font-medium text-amber-900"
                title={`Update available: ${device.firmware_available}`}
              >
                ↑
              </span>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground/40">—</span>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 align-top">
        {device ? <StatusPill status={device.status} /> : null}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 align-top text-right">
        {device ? (
          <Link
            href={`/dashboard/devices/${device.id}`}
            className="text-xs text-primary hover:underline"
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
