"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useParams } from "next/navigation";
import type { ReactNode } from "react";

import { StatusPill } from "@/components/status-pill";
import { VendorIcon } from "@/components/vendor-icon";
import {
  capabilitiesFor,
  DRIVERS_QUERY_KEY,
  listDrivers,
  type Driver,
} from "@/lib/drivers";
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

  const { data: drivers } = useQuery<Driver[]>({
    queryKey: DRIVERS_QUERY_KEY,
    queryFn: listDrivers,
    staleTime: 5 * 60_000,
  });
  const caps = capabilitiesFor(drivers, device?.vendor);

  // Each tab names the capability that makes it meaningful. A driver that
  // lacks it gets no tab — which is the whole point of the capability set,
  // and stops a Linux host offering DHCP or a RouterOS log viewer.
  // `needs: null` means "always relevant".
  const ALL_TABS: { href: string; label: string; needs: string[] | null }[] = [
    { href: base, label: "Overview", needs: null },
    { href: `${base}/services`, label: "IP services", needs: ["ip.service"] },
    { href: `${base}/system-users`, label: "Device users", needs: ["system.user"] },
    {
      href: `${base}/vpn`,
      label: "VPN",
      needs: ["ppp.secret", "vpn.wireguard.interface", "vpn.l2tp"],
    },
    {
      href: `${base}/firewall`,
      label: "Firewall",
      needs: ["firewall.filter", "firewall.nat"],
    },
    {
      href: `${base}/network`,
      label: "Network",
      needs: ["interface.list", "ip.address", "ip.route"],
    },
    { href: `${base}/dhcp`, label: "DHCP", needs: ["dhcp.server", "dhcp.lease"] },
    { href: `${base}/queues`, label: "Queues", needs: ["queue.simple"] },
    { href: `${base}/storage`, label: "Storage", needs: ["disk.usage"] },
    { href: `${base}/processes`, label: "Processes", needs: ["proc.list"] },
    { href: `${base}/scheduled`, label: "Scheduled", needs: ["cron"] },
    { href: `${base}/logs`, label: "Logs", needs: ["system.log"] },
    { href: `${base}/system`, label: "System", needs: ["system.info"] },
    { href: `${base}/backups`, label: "Backups", needs: ["system.backup"] },
  ];

  // Until the driver list lands, show everything rather than flashing an
  // empty strip and then filling it in.
  const tabs = caps
    ? ALL_TABS.filter((t) => !t.needs || t.needs.some((c) => caps.has(c)))
    : ALL_TABS;

  return (
    <div>
      {/* Sticky contextual header — Tailwind UI "Breadcrumbs with chevrons"
          variant so it lines up with the rest of the app's standard look. */}
      <div className="sticky top-0 z-20 -mx-4 -mt-8 mb-4 border-b border-border bg-background/85 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/70">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <nav className="flex" aria-label="Breadcrumb">
            <ol role="list" className="flex items-center space-x-2">
              <li>
                <Link
                  href="/dashboard"
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="Home"
                >
                  <HomeIcon className="size-4 shrink-0" aria-hidden="true" />
                  <span className="sr-only">Home</span>
                </Link>
              </li>
              <BreadcrumbItem
                href="/dashboard/devices"
                label="Devices"
                current={false}
              />
              <BreadcrumbItem
                href={tenant ? `/dashboard/tenants/${tenant.id}` : undefined}
                label={tenant?.name ?? "…"}
                current={false}
              />
              <BreadcrumbItem
                href={site ? `/dashboard/sites/${site.id}` : undefined}
                label={site?.name ?? "…"}
                current={false}
              />
              <BreadcrumbItem
                href={undefined}
                label={device?.name ?? "…"}
                current={true}
              />
            </ol>
          </nav>
          {device && (
            <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
              <StatusPill status={device.status} />
              <span className="font-mono">
                {device.host}:{device.device_class === "server" ? device.ssh_port : device.port}
              </span>
              <span className="flex items-center gap-1.5">
                ·
                <VendorIcon
                  vendor={device.vendor}
                  deviceClass={device.device_class}
                  osFamily={device.os_family}
                  osVersion={device.os_version}
                  className="size-4"
                />
                {device.device_class === "server"
                  ? (device.os_version ?? "Linux")
                  : device.vendor}
              </span>
            </div>
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

function BreadcrumbItem({
  href,
  label,
  current,
}: {
  href: string | undefined;
  label: string;
  current: boolean;
}) {
  // Render as a chevron + label pair. Matches the Tailwind UI breadcrumb
  // pattern: separator lives inside the same <li> as the link it precedes.
  return (
    <li>
      <div className="flex items-center">
        <ChevronRightIcon
          className="size-4 shrink-0 text-muted-foreground/60"
          aria-hidden="true"
        />
        {href ? (
          <Link
            href={href}
            className="ml-2 text-sm font-medium text-muted-foreground hover:text-foreground"
            aria-current={current ? "page" : undefined}
          >
            {label}
          </Link>
        ) : (
          <span
            className={
              current
                ? "ml-2 text-sm font-semibold text-foreground"
                : "ml-2 text-sm font-medium text-muted-foreground"
            }
            aria-current={current ? "page" : undefined}
          >
            {label}
          </span>
        )}
      </div>
    </li>
  );
}

function HomeIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" {...props}>
      <path
        fillRule="evenodd"
        d="M9.293 2.293a1 1 0 011.414 0l7 7A1 1 0 0117 11h-1v6a1 1 0 01-1 1h-3a1 1 0 01-1-1v-3H9v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-6H3a1 1 0 01-.707-1.707l7-7z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ChevronRightIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="currentColor" {...props}>
      <path
        fillRule="evenodd"
        d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
        clipRule="evenodd"
      />
    </svg>
  );
}
