"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { listDevices, type Device } from "@/lib/devices";
import { listSites, type Site } from "@/lib/sites";

export default function DashboardPage() {
  const { data: sites } = useQuery<Site[]>({ queryKey: ["sites"], queryFn: listSites });
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });

  const total = devices?.length ?? 0;
  const online = devices?.filter((d) => d.status === "online").length ?? 0;
  const errors = devices?.filter((d) => d.status === "error").length ?? 0;
  const offline = devices?.filter((d) => d.status === "offline").length ?? 0;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Fleet summary across all your sites.
      </p>

      <div className="mt-8 grid gap-4 md:grid-cols-4">
        <Card
          title="Sites"
          value={sites?.length ?? 0}
          href="/dashboard/sites"
          hint="MSP clients"
        />
        <Card
          title="Devices"
          value={total}
          href="/dashboard/devices"
          hint={`${online} online · ${offline} offline · ${errors} error`}
        />
        <Card title="Active sessions" value="—" hint="Real-time in Phase 6" />
        <Card title="Audit events (24h)" value="—" hint="Coming in Phase 4" />
      </div>

      {total === 0 && (
        <div className="mt-8 rounded-lg border border-dashed border-border bg-card p-6 text-sm">
          <p className="font-medium">Getting started</p>
          <ol className="mt-3 list-decimal space-y-2 pl-5 text-muted-foreground">
            <li>
              <Link href="/dashboard/sites" className="text-primary hover:underline">
                Create your first site
              </Link>{" "}
              (an MSP client)
            </li>
            <li>
              <Link href="/dashboard/devices" className="text-primary hover:underline">
                Add a MikroTik device
              </Link>{" "}
              with its API credentials
            </li>
            <li>Click <strong>Test connection</strong> on the device detail page</li>
          </ol>
        </div>
      )}
    </div>
  );
}

function Card({
  title,
  value,
  hint,
  href,
}: {
  title: string;
  value: string | number;
  hint?: string;
  href?: string;
}) {
  const inner = (
    <div className="rounded-lg border border-border bg-card p-5 transition hover:border-primary/40">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{title}</p>
      <p className="mt-1 text-3xl font-semibold">{value}</p>
      {hint && <p className="mt-2 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}
