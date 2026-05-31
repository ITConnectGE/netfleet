"use client";

// Dashboard-level "where are my sites?" map. Renders one marker per site
// that has lat/lon, colour-coded by the status of its devices:
//   green  — every device is online
//   amber  — some online, some offline (or status=unknown)
//   red    — at least one device is offline or in error
//   grey   — no devices have been added yet
//
// Click a marker for a popup with the device list and quick links into
// the device detail pages.

import L from "leaflet";
import Link from "next/link";
import { useMemo } from "react";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";

import type { Device } from "@/lib/devices";
import type { Site } from "@/lib/sites";

type Health = "green" | "amber" | "red" | "grey";

function siteHealth(devices: Device[]): Health {
  if (devices.length === 0) return "grey";
  const online = devices.filter((d) => d.status === "online").length;
  const offline = devices.filter((d) => d.status === "offline" || d.status === "error").length;
  if (offline > 0) return "red";
  if (online < devices.length) return "amber";
  return "green";
}

const COLOURS: Record<Health, { fill: string; stroke: string }> = {
  green: { fill: "#10b981", stroke: "#064e3b" },
  amber: { fill: "#f59e0b", stroke: "#78350f" },
  red: { fill: "#ef4444", stroke: "#7f1d1d" },
  grey: { fill: "#9ca3af", stroke: "#374151" },
};

function pin(health: Health): L.DivIcon {
  const c = COLOURS[health];
  return L.divIcon({
    html: `<svg viewBox="0 0 32 40" width="32" height="40" xmlns="http://www.w3.org/2000/svg">
      <path d="M16 0C7.16 0 0 7.16 0 16c0 12 16 24 16 24s16-12 16-24C32 7.16 24.84 0 16 0z"
            fill="${c.fill}" stroke="${c.stroke}" stroke-width="1.5"/>
      <circle cx="16" cy="16" r="6" fill="white"/>
    </svg>`,
    className: "",
    iconSize: [32, 40],
    iconAnchor: [16, 40],
    popupAnchor: [0, -40],
  });
}

export default function FleetMap({
  sites,
  devices,
}: {
  sites: Site[];
  devices: Device[];
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
          const health = siteHealth(siteDevices);
          return (
            <Marker
              key={s.id}
              position={[s.latitude, s.longitude]}
              icon={pin(health)}
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
    health === "green" ? "all online" :
    health === "amber" ? "mixed" :
    health === "red" ? "issue" : "empty";
  const cls =
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
