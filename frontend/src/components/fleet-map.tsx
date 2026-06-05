"use client";

// Dashboard-level "where are my sites?" map. Renders one marker per site
// that has lat/lon, colour-coded by both the device status of the site
// and whether any unacknowledged critical events are sitting on those
// devices:
//   critical (dark red) — at least one unack critical-severity event
//   red                 — a device is offline or errored
//   amber               — some online, some offline / unknown
//   green               — every device online + no unack criticals
//   grey                — no devices have been added yet
//
// Critical wins over every device-status colour because that's the
// "wake me up at 3 AM" tier — an operator scanning the map should
// always see those first.

import L from "leaflet";
import Link from "next/link";
import { useMemo } from "react";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";

import type { Device } from "@/lib/devices";
import type { Severity } from "@/lib/events";
import type { Site } from "@/lib/sites";

type Health = "green" | "amber" | "red" | "grey" | "critical";

function siteHealth(
  devices: Device[],
  unackBySeverity: Record<Severity, number> | undefined,
): Health {
  // Critical-severity events are the highest priority tier — they
  // override device status colouring so an operator can't miss them
  // even when every device on the site happens to be polling green.
  if (unackBySeverity && unackBySeverity.critical > 0) return "critical";
  if (devices.length === 0) return "grey";
  const online = devices.filter((d) => d.status === "online").length;
  const offline = devices.filter(
    (d) => d.status === "offline" || d.status === "error",
  ).length;
  if (offline > 0) return "red";
  if (online < devices.length) return "amber";
  return "green";
}

const COLOURS: Record<Health, { fill: string; stroke: string }> = {
  // Stroke is one shade darker than fill so the silhouette stays
  // readable at every zoom level. Critical uses a deep wine-red so
  // it pops against the plain red "device down" marker without
  // looking like an opaque black box on dark map tiles.
  critical: { fill: "#7f1d1d", stroke: "#450a0a" },
  red: { fill: "#ef4444", stroke: "#7f1d1d" },
  amber: { fill: "#f59e0b", stroke: "#78350f" },
  green: { fill: "#10b981", stroke: "#064e3b" },
  grey: { fill: "#9ca3af", stroke: "#374151" },
};

// Stack the layers so issue markers float above healthy ones when sites
// overlap on the map (think two clients in the same building). Without
// this the iteration order decides who's on top, which means a green
// "everything fine" marker can hide a red "something's down" marker
// directly beneath it — exactly what we don't want.
const Z_INDEX_BY_HEALTH: Record<Health, number> = {
  critical: 4000,
  red: 3000,
  amber: 2000,
  grey: 500,
  green: 0,
};

/** Cleaner, taller pin SVG with a soft ground shadow so the marker
 *  reads as a 3D pin instead of a flat blob — earlier rounder shape
 *  could look like a box when the browser anti-aliased the curves
 *  away at low zoom. The viewBox is taller to give the point room
 *  without scaling the head down. */
function pin(health: Health): L.DivIcon {
  const c = COLOURS[health];
  const isCritical = health === "critical";
  return L.divIcon({
    html: `<svg viewBox="0 0 30 44" width="30" height="44" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <filter id="pin-shadow" x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow dx="0" dy="1.5" stdDeviation="1.2" flood-opacity="0.35"/>
        </filter>
      </defs>
      <ellipse cx="15" cy="41" rx="5" ry="1.6" fill="rgba(0,0,0,0.35)"/>
      <path
        d="M15 1.5 C7.5 1.5 1.5 7.5 1.5 15 C1.5 22 7 28 15 41 C23 28 28.5 22 28.5 15 C28.5 7.5 22.5 1.5 15 1.5 Z"
        fill="${c.fill}"
        stroke="${c.stroke}"
        stroke-width="1.6"
        stroke-linejoin="round"
        filter="url(#pin-shadow)"
      />
      <circle cx="15" cy="15" r="5" fill="white"/>
      ${
        isCritical
          ? `<text x="15" y="18.3" text-anchor="middle" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="8" font-weight="700" fill="${c.fill}">!</text>`
          : ""
      }
    </svg>`,
    className: "",
    iconSize: [30, 44],
    iconAnchor: [15, 44],
    popupAnchor: [0, -42],
  });
}

export default function FleetMap({
  sites,
  devices,
  unackBySite,
}: {
  sites: Site[];
  devices: Device[];
  unackBySite?: Record<string, Record<Severity, number>>;
}) {
  const located = sites.filter(
    (s): s is Site & { latitude: number; longitude: number } =>
      s.latitude !== null && s.longitude !== null,
  );

  // devicesPerSite for the popup; computed once per render.
  const devicesPerSite = useMemo(() => {
    const m = new Map<string, Device[]>();
    for (const d of devices) {
      const list = m.get(d.site_id) ?? [];
      list.push(d);
      m.set(d.site_id, list);
    }
    return m;
  }, [devices]);

  // Pick a sensible centre — average of marker positions, fallback to
  // Tbilisi when nothing is located yet.
  const center: [number, number] = useMemo(() => {
    if (located.length === 0) return [41.7151, 44.8271];
    const sumLat = located.reduce((a, s) => a + s.latitude, 0);
    const sumLng = located.reduce((a, s) => a + s.longitude, 0);
    return [sumLat / located.length, sumLng / located.length];
  }, [located]);

  if (located.length === 0) {
    return (
      <div className="flex h-72 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
        <p>No site has a location yet.</p>
        <p className="mt-1 text-xs">
          Open <Link href="/dashboard/sites" className="text-primary hover:underline">Sites</Link>,
          edit a site, drop a pin on the map and save.
        </p>
      </div>
    );
  }

  return (
    <div className="h-[28rem] overflow-hidden rounded-lg border border-border">
      <MapContainer
        center={center}
        zoom={located.length === 1 ? 13 : 6}
        scrollWheelZoom
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {located.map((s) => {
          const siteDevices = devicesPerSite.get(s.id) ?? [];
          const siteUnack = unackBySite?.[s.id];
          const health = siteHealth(siteDevices, siteUnack);
          return (
            <Marker
              key={s.id}
              position={[s.latitude, s.longitude]}
              icon={pin(health)}
              zIndexOffset={Z_INDEX_BY_HEALTH[health]}
            >
              <Popup>
                <div className="min-w-[220px]">
                  <div className="flex items-center justify-between gap-2">
                    <strong className="text-sm">{s.name}</strong>
                    <HealthChip health={health} />
                  </div>
                  {s.address && (
                    <p className="mt-1 text-xs text-zinc-500">{s.address}</p>
                  )}
                  {siteUnack && siteUnack.critical > 0 && (
                    <p className="mt-1 text-xs font-medium text-red-700">
                      {siteUnack.critical} unacknowledged critical event
                      {siteUnack.critical === 1 ? "" : "s"}
                    </p>
                  )}
                  <div className="mt-2 space-y-0.5 text-xs">
                    {siteDevices.length === 0 && (
                      <span className="text-zinc-500">no devices added yet</span>
                    )}
                    {siteDevices.map((d) => (
                      <div key={d.id} className="flex items-center justify-between gap-2">
                        <Link
                          href={`/dashboard/devices/${d.id}`}
                          className="text-blue-700 hover:underline"
                        >
                          {d.name}
                        </Link>
                        <DeviceStatusDot status={d.status} />
                      </div>
                    ))}
                  </div>
                  <Link
                    href={`/dashboard/sites/${s.id}`}
                    className="mt-2 inline-block text-[11px] text-blue-700 hover:underline"
                  >
                    Open site →
                  </Link>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
    </div>
  );
}

function HealthChip({ health }: { health: Health }) {
  const label =
    health === "critical" ? "critical" :
    health === "green" ? "all online" :
    health === "amber" ? "mixed" :
    health === "red" ? "issue" : "empty";
  const cls =
    health === "critical" ? "bg-red-900 text-red-50" :
    health === "green" ? "bg-emerald-100 text-emerald-800" :
    health === "amber" ? "bg-amber-100 text-amber-800" :
    health === "red" ? "bg-red-100 text-red-800" :
    "bg-zinc-200 text-zinc-700";
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {label}
    </span>
  );
}

function DeviceStatusDot({ status }: { status: string }) {
  const c =
    status === "online" ? "#10b981" :
    status === "offline" ? "#ef4444" :
    status === "error" ? "#dc2626" : "#9ca3af";
  return (
    <span
      title={status}
      style={{ background: c }}
      className="inline-block size-2.5 shrink-0 rounded-full"
    />
  );
}
