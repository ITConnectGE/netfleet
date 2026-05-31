"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useParams } from "next/navigation";
import type { ReactNode } from "react";

import { StatusPill } from "@/components/status-pill";
import { getDevice, type Device } from "@/lib/devices";
import { getSite, type Site } from "@/lib/sites";
import { getTenant, type Tenant } from "@/lib/tenants";
import { cn } from "@/lib/utils";

export default function DeviceLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  const base = `/dashboard/devices/${params.id}`;

  const { data: device } = useQuery<Device>({
    queryKey: ["device", params.id],
    queryFn: () => getDevice(params.id),
    enabled: Boolean(params.id),
  });
  const { data: site } = useQuery<Site>({
    queryKey: ["site", device?.site_id],
    queryFn: () => getSite(device!.site_id),
    enabled: Boolean(device?.site_id),
  });
  const { data: tenant } = useQuery<Tenant>({
    queryKey: ["tenant", site?.tenant_id],
    queryFn: () => getTenant(site!.tenant_id),
    enabled: Boolean(site?.tenant_id),
  });

  const tabs = [
    { href: base, label: "Overview" },
    { href: `${base}/services`, label: "IP services" },
    { href: `${base}/system-users`, label: "Device users" },
    { href: `${base}/vpn`, label: "VPN" },
    { href: `${base}/firewall`, label: "Firewall" },
    { href: `${base}/network`, label: "Network" },
    { href: `${base}/queues`, label: "Queues" },
    { href: `${base}/logs`, label: "Logs" },
    { href: `${base}/system`, label: "System" },
    { href: `${base}/backups`, label: "Backups" },
  ] as const;

  return (
    <div>
      {/* Sticky contextual header — visible from every device sub-page so
          the user always knows which client / site / box they're operating
          on. */}
      <div className="sticky top-0 z-20 -mx-4 -mt-8 mb-4 border-b border-border bg-background/85 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/70">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <Link
            href="/dashboard/devices"
            className="text-muted-foreground hover:text-foreground hover:underline"
          >
            ← Devices
          </Link>
          <span className="text-muted-foreground">·</span>
          {tenant ? (
            <Link
              href={`/dashboard/tenants/${tenant.id}`}
              className="font-medium text-muted-foreground hover:text-foreground hover:underline"
            >
              {tenant.name}
            </Link>
          ) : (
            <span className="text-muted-foreground">…</span>
          )}
          <span className="text-muted-foreground">/</span>
          {site ? (
            <Link
              href={`/dashboard/sites/${site.id}`}
              className="font-medium text-muted-foreground hover:text-foreground hover:underline"
            >
              {site.name}
            </Link>
          ) : (
            <span className="text-muted-foreground">…</span>
          )}
          <span className="text-muted-foreground">/</span>
          <span className="text-base font-semibold text-foreground">
            {device?.name ?? "…"}
          </span>
          {device && (
            <span className="ml-2 inline-flex items-center gap-2 text-xs text-muted-foreground">
              <StatusPill status={device.status} />
              <span className="font-mono">
                {device.host}:{device.port}
              </span>
              <span>· {device.vendor}</span>
            </span>
          )}
        </div>
      </div>

      <nav className="mb-6 flex flex-wrap gap-1 border-b border-border">
        {tabs.map((t) => {
          const active =
            t.href === base ? pathname === base : pathname.startsWith(t.href);
          return (
            <Link
              key={t.href}
              href={t.href}
              className={cn(
                "border-b-2 px-3 py-2 text-sm font-medium transition",
                active
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}
