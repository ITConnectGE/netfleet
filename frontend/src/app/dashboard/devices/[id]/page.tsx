"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { StatusPill } from "@/components/status-pill";
import {
  deleteDevice,
  getDevice,
  testDeviceConnection,
  updateDevice,
  type Device,
  type TestConnectionResult,
} from "@/lib/devices";
import { listDrivers, type Driver } from "@/lib/drivers";
import { getSite, listSites, type Site } from "@/lib/sites";
import { useRouter } from "next/navigation";

export default function DeviceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const id = params.id;

  const { data: device, isLoading } = useQuery<Device>({
    queryKey: ["device", id],
    queryFn: () => getDevice(id),
    enabled: Boolean(id),
  });
  const { data: site } = useQuery<Site>({
    queryKey: ["site", device?.site_id],
    queryFn: () => getSite(device!.site_id),
    enabled: Boolean(device?.site_id),
  });
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: listSites,
  });
  const { data: drivers } = useQuery<Driver[]>({ queryKey: ["drivers"], queryFn: listDrivers });

  const moveSite = useMutation({
    mutationFn: (newSiteId: string) => updateDevice(id, { site_id: newSiteId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["device", id] });
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["sites"] });
    },
  });

  const test = useMutation<TestConnectionResult>({
    mutationFn: () => testDeviceConnection(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device", id] }),
  });

  const del = useMutation({
    mutationFn: () => deleteDevice(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      router.replace("/dashboard/devices");
    },
  });

  if (isLoading || !device) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const driver = drivers?.find((d) => d.vendor === device.vendor);

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <Link href="/dashboard/devices" className="text-xs text-muted-foreground hover:underline">
            ← Devices
          </Link>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{device.name}</h1>
          <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            <span>{driver?.display_name ?? device.vendor}</span>
            {site && (
              <>
                <span>·</span>
                <Link href={`/dashboard/sites/${site.id}`} className="hover:underline">
                  {site.name}
                </Link>
              </>
            )}
            {sites && sites.length > 1 && (
              <MoveSiteControl
                currentSiteId={device.site_id}
                sites={sites}
                onMove={(newId) => moveSite.mutate(newId)}
                pending={moveSite.isPending}
              />
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => test.mutate()}
            disabled={test.isPending}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
          >
            {test.isPending ? "Testing…" : "Test connection"}
          </button>
          <button
            onClick={() => {
              if (confirm(`Delete device "${device.name}"? This cannot be undone.`)) {
                del.mutate();
              }
            }}
            disabled={del.isPending}
            className="rounded-md border border-destructive/40 bg-background px-3 py-1.5 text-sm font-medium text-destructive transition hover:bg-destructive/10 disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      </div>

      {test.data && (
        <div
          className={`mt-6 rounded-md border px-4 py-3 text-sm ${
            test.data.ok
              ? "border-emerald-300 bg-emerald-50 text-emerald-900"
              : "border-red-300 bg-red-50 text-red-900"
          }`}
        >
          {test.data.ok ? (
            <>
              <strong>Connection OK.</strong> Identity:{" "}
              <span className="font-mono">{test.data.identity}</span>
              {test.data.model && <> · Model: {test.data.model}</>}
              {test.data.firmware && <> · Firmware: {test.data.firmware}</>}
            </>
          ) : (
            <>
              <strong>Connection failed:</strong> {test.data.error ?? test.data.status}
            </>
          )}
        </div>
      )}

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Section title="Connection">
          <Row label="Status">
            <StatusPill status={device.status} />
          </Row>
          <Row label="Host">
            <span className="font-mono">
              {device.host}:{device.port}
            </span>
          </Row>
          <Row label="Transport">{device.transport}</Row>
          <Row label="Username">
            <span className="font-mono">{device.username}</span>
          </Row>
          <Row label="Credentials">
            {device.has_password && <Pill>password</Pill>}
            {device.has_api_key && <Pill>api_key</Pill>}
            {!device.has_password && !device.has_api_key && (
              <span className="text-muted-foreground">none</span>
            )}
          </Row>
          <Row label="Verify TLS">{device.verify_tls ? "Yes" : "No"}</Row>
          <Row label="Enabled">{device.is_enabled ? "Yes" : "No"}</Row>
        </Section>

        <Section title="Discovered">
          <Row label="Model">{device.model ?? "—"}</Row>
          <Row label="Firmware">{device.firmware ?? "—"}</Row>
          <Row label="Serial">{device.serial ?? "—"}</Row>
          <Row label="Last seen">
            {device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : "—"}
          </Row>
          {device.status_error && (
            <Row label="Last error">
              <span className="font-mono text-xs">{device.status_error}</span>
            </Row>
          )}
        </Section>
      </div>

      {driver && (
        <Section title={`${driver.display_name} — capabilities`}>
          <div className="flex flex-wrap gap-1.5">
            {driver.capabilities.map((c) => (
              <Pill key={c}>{c}</Pill>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Operating these sections is added in Phase 5 (MikroTik driver complete).
          </p>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <h2 className="mb-3 text-sm font-medium text-muted-foreground">{title}</h2>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex rounded-md bg-muted px-2 py-0.5 font-mono text-xs">
      {children}
    </span>
  );
}

function MoveSiteControl({
  currentSiteId,
  sites,
  onMove,
  pending,
}: {
  currentSiteId: string;
  sites: Site[];
  onMove: (newSiteId: string) => void;
  pending: boolean;
}) {
  const [editing, setEditing] = useState(false);
  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="rounded-md border border-input bg-background px-2 py-0.5 text-xs font-medium transition hover:bg-accent"
      >
        Move…
      </button>
    );
  }
  const others = sites.filter((s) => s.id !== currentSiteId);
  return (
    <div className="flex items-center gap-1">
      <select
        defaultValue=""
        disabled={pending}
        onChange={(e) => {
          const target = e.target.value;
          if (!target) return;
          if (confirm(`Move this device to "${sites.find((s) => s.id === target)?.name}"?`)) {
            onMove(target);
          }
          setEditing(false);
        }}
        className="rounded-md border border-input bg-background px-2 py-0.5 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <option value="">— move to site —</option>
        {others.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => setEditing(false)}
        className="rounded-md px-1.5 py-0.5 text-xs text-muted-foreground hover:text-foreground"
      >
        cancel
      </button>
    </div>
  );
}
