"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import Link from "next/link";

import { listDevices, type Device } from "@/lib/devices";
import { eventsSummary, type Severity } from "@/lib/events";
import { getFleetFirmwareSummary, type FleetFirmwareSummary } from "@/lib/firmware";
import { listSites, type Site } from "@/lib/sites";

const FleetMap = dynamic(() => import("@/components/fleet-map"), {
  ssr: false,
  loading: () => <div className="h-[28rem] animate-pulse rounded-lg bg-muted" />,
});

interface EventsSummary {
  unacknowledged_total: number;
  by_severity: Record<Severity, number>;
}

export default function DashboardPage() {
  const { data: sites } = useQuery<Site[]>({ queryKey: ["sites"], queryFn: () => listSites() });
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const { data: fw } = useQuery<FleetFirmwareSummary>({
    queryKey: ["firmware-summary"],
    queryFn: getFleetFirmwareSummary,
  });
  const { data: events } = useQuery<EventsSummary>({
    queryKey: ["events-summary"],
    queryFn: eventsSummary,
    refetchInterval: 30_000,
  });

  const total = devices?.length ?? 0;
  const online = devices?.filter((d) => d.status === "online").length ?? 0;
  const errors = devices?.filter((d) => d.status === "error").length ?? 0;
  const offline = devices?.filter((d) => d.status === "offline").length ?? 0;

  const allUpToDate =
    fw !== undefined &&
    fw.total > 0 &&
    fw.updates_available === 0 &&
    fw.never_checked === 0;

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
        <Card
          title="Firmware updates"
          value={
            allUpToDate ? (
              <span className="inline-flex items-baseline gap-2">
                <span>0</span>
                <CheckBadge />
              </span>
            ) : (
              fw?.updates_available ?? "—"
            )
          }
          href={
            fw && (fw.updates_available ?? 0) > 0
              ? "/dashboard/devices?firmware=available"
              : "/dashboard/devices"
          }
          hint={
            fw
              ? allUpToDate
                ? "all devices up to date"
                : `${fw.checked_ever} of ${fw.total} checked${
                    fw.never_checked > 0 ? ` · ${fw.never_checked} never checked` : ""
                  }`
              : "checked nightly"
          }
        />
        <Card
          title="Unack events"
          value={events?.unacknowledged_total ?? "—"}
          href="/dashboard/events"
          hint={
            events
              ? `${events.by_severity.critical ?? 0} critical · ${
                  events.by_severity.error ?? 0
                } error · ${events.by_severity.warning ?? 0} warning`
              : "scanned every 5 min"
          }
        />
      </div>

      <section className="mt-10">
        <div className="mb-3 flex items-end justify-between">
          <div>
            <h2 className="text-lg font-semibold">Fleet map</h2>
            <p className="text-xs text-muted-foreground">
              Sites with a saved location. Click a marker to see its devices.
              Free tiles courtesy of OpenStreetMap.
            </p>
          </div>
          <Link
            href="/dashboard/tenants"
            className="text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            Add a location →
          </Link>
        </div>
        <FleetMap sites={sites ?? []} devices={devices ?? []} />
      </section>

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
  value: string | number | React.ReactNode;
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

function CheckBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800"
      title="All devices up to date"
    >
      <svg
        viewBox="0 0 20 20"
        className="size-3"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M16.704 5.296a1 1 0 010 1.414l-7.95 7.95a1 1 0 01-1.415 0L3.296 10.61a1 1 0 011.414-1.414l3.336 3.336 7.243-7.236a1 1 0 011.415 0z"
          clipRule="evenodd"
        />
      </svg>
      up to date
    </span>
  );
}
