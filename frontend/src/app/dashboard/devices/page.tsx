"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { StatusPill } from "@/components/status-pill";
import {
  createDevice,
  listDevices,
  testDeviceConnection,
  type Device,
} from "@/lib/devices";
import { listDrivers, type Driver } from "@/lib/drivers";
import { listSites, type Site } from "@/lib/sites";

export default function DevicesPage() {
  const qc = useQueryClient();
  const { data: devices, isLoading } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const { data: sites } = useQuery<Site[]>({ queryKey: ["sites"], queryFn: listSites });
  const { data: drivers } = useQuery<Driver[]>({ queryKey: ["drivers"], queryFn: listDrivers });
  const [showForm, setShowForm] = useState(false);

  const siteIndex = Object.fromEntries((sites ?? []).map((s) => [s.id, s.name]));
  const vendorIndex = Object.fromEntries((drivers ?? []).map((d) => [d.vendor, d.display_name]));

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Devices</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            All network devices across your sites. Add MikroTik routers, FortiGate firewalls (soon), and more.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          disabled={!sites || sites.length === 0}
          title={!sites || sites.length === 0 ? "Create a site first" : ""}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {showForm ? "Cancel" : "+ New device"}
        </button>
      </div>

      {(!sites || sites.length === 0) && (
        <div className="mt-6 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          You don&apos;t have any sites yet.{" "}
          <Link href="/dashboard/sites" className="font-medium underline">
            Create a site
          </Link>{" "}
          before adding a device.
        </div>
      )}

      {showForm && sites && drivers && (
        <DeviceForm
          sites={sites}
          drivers={drivers}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["devices"] });
            qc.invalidateQueries({ queryKey: ["sites"] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Site</th>
              <th className="px-4 py-2.5 font-medium">Vendor</th>
              <th className="px-4 py-2.5 font-medium">Host</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (!devices || devices.length === 0) && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  No devices yet.
                </td>
              </tr>
            )}
            {devices?.map((d) => (
              <DeviceRow
                key={d.id}
                device={d}
                siteName={siteIndex[d.site_id] ?? "—"}
                vendorName={vendorIndex[d.vendor] ?? d.vendor}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DeviceRow({
  device,
  siteName,
  vendorName,
}: {
  device: Device;
  siteName: string;
  vendorName: string;
}) {
  return (
    <tr className="hover:bg-accent/30">
      <td className="px-4 py-3 font-medium">
        <Link href={`/dashboard/devices/${device.id}`} className="hover:underline">
          {device.name}
        </Link>
      </td>
      <td className="px-4 py-3 text-muted-foreground">{siteName}</td>
      <td className="px-4 py-3">{vendorName}</td>
      <td className="px-4 py-3 font-mono text-xs">
        {device.host}:{device.port}
      </td>
      <td className="px-4 py-3">
        <StatusPill status={device.status} />
      </td>
      <td className="px-4 py-3 text-right">
        <Link
          href={`/dashboard/devices/${device.id}`}
          className="text-xs text-primary hover:underline"
        >
          Details →
        </Link>
      </td>
    </tr>
  );
}


function DeviceForm({
  sites,
  drivers,
  onCreated,
}: {
  sites: Site[];
  drivers: Driver[];
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [siteId, setSiteId] = useState(sites[0]?.id ?? "");
  const [vendor, setVendor] = useState(drivers[0]?.vendor ?? "mikrotik");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(8728);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [verifyTls, setVerifyTls] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sensible default port per vendor (MikroTik native API = 8728, REST = 443)
  useEffect(() => {
    if (vendor === "mikrotik") setPort(8728);
  }, [vendor]);

  const m = useMutation({
    mutationFn: () =>
      createDevice({
        name,
        site_id: siteId,
        vendor,
        host,
        port,
        username,
        password: password || null,
        verify_tls: verifyTls,
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    m.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="mt-6 rounded-lg border border-border bg-card p-5">
      {error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Display name" htmlFor="d-name">
          <input
            id="d-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
            placeholder="Office CCR"
          />
        </Field>
        <Field label="Site" htmlFor="d-site">
          <select
            id="d-site"
            required
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
            className={inputClass}
          >
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Vendor" htmlFor="d-vendor">
          <select
            id="d-vendor"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            className={inputClass}
          >
            {drivers.map((d) => (
              <option key={d.vendor} value={d.vendor}>
                {d.display_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Host" htmlFor="d-host">
          <input
            id="d-host"
            required
            value={host}
            onChange={(e) => setHost(e.target.value)}
            className={`${inputClass} font-mono`}
            placeholder="192.0.2.10 or router.client-a.local"
          />
        </Field>
        <Field label="Port" htmlFor="d-port">
          <input
            id="d-port"
            type="number"
            min={1}
            max={65535}
            value={port}
            onChange={(e) => setPort(Number(e.target.value))}
            className={inputClass}
          />
        </Field>
        <Field label="Verify TLS" htmlFor="d-tls">
          <label className="flex items-center gap-2 text-sm">
            <input
              id="d-tls"
              type="checkbox"
              checked={verifyTls}
              onChange={(e) => setVerifyTls(e.target.checked)}
              className="size-4 rounded"
            />
            Reject untrusted certificates
          </label>
        </Field>
        <Field label="Username" htmlFor="d-user">
          <input
            id="d-user"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className={inputClass}
            autoComplete="off"
          />
        </Field>
        <Field label="Password" htmlFor="d-pass" hint="encrypted at rest">
          <input
            id="d-pass"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
            autoComplete="new-password"
          />
        </Field>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Adding…" : "Add device"}
        </button>
      </div>
    </form>
  );
}

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
        {hint && <span className="ml-2 text-xs font-normal text-muted-foreground">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

