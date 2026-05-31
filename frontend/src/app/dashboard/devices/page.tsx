"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { StatusPill } from "@/components/status-pill";
import {
  createDevice,
  getOnboardingScript,
  listDevices,
  testDeviceConnection,
  type Device,
} from "@/lib/devices";
import { listDrivers, type Driver } from "@/lib/drivers";
import { listSites, type Site } from "@/lib/sites";

export default function DevicesPage() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const firmwareFilter = searchParams.get("firmware"); // "available" | null
  const statusFilter = searchParams.get("status"); // "online" | "offline" | "error" | null

  const { data: devices, isLoading } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const { data: sites } = useQuery<Site[]>({ queryKey: ["sites"], queryFn: () => listSites() });
  const { data: drivers } = useQuery<Driver[]>({ queryKey: ["drivers"], queryFn: listDrivers });
  const [showForm, setShowForm] = useState(false);

  const siteIndex = Object.fromEntries((sites ?? []).map((s) => [s.id, s.name]));
  const vendorIndex = Object.fromEntries((drivers ?? []).map((d) => [d.vendor, d.display_name]));

  // Derived row set after filters. Kept here so the empty-state and the
  // counter pill both reflect the active filter.
  const filtered = useMemo(() => {
    if (!devices) return undefined;
    return devices.filter((d) => {
      if (statusFilter && d.status !== statusFilter) return false;
      if (firmwareFilter === "available") {
        const osUp =
          d.firmware_available &&
          d.firmware &&
          d.firmware_available !== d.firmware;
        const rbUp =
          d.routerboard_available &&
          d.routerboard_current &&
          d.routerboard_available !== d.routerboard_current;
        if (!osUp && !rbUp) return false;
      }
      return true;
    });
  }, [devices, firmwareFilter, statusFilter]);
  const activeFilter = firmwareFilter === "available" ? "firmware updates" : statusFilter ?? null;

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

      {activeFilter && (
        <div className="mt-4 flex items-center justify-between rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          <span>
            Filtered by <strong>{activeFilter}</strong> — showing{" "}
            {filtered?.length ?? 0} of {devices?.length ?? 0} devices.
          </span>
          <Link
            href="/dashboard/devices"
            className="font-medium underline-offset-2 hover:underline"
          >
            Clear
          </Link>
        </div>
      )}

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Site</th>
              <th className="px-4 py-2.5 font-medium">Vendor</th>
              <th className="px-4 py-2.5 font-medium">Host</th>
              <th className="px-4 py-2.5 font-medium">Firmware</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && filtered && filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">
                  {activeFilter
                    ? `No devices match the ${activeFilter} filter.`
                    : "No devices yet."}
                </td>
              </tr>
            )}
            {filtered?.map((d) => (
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
  const osUpgrade =
    device.firmware_available &&
    device.firmware &&
    device.firmware_available !== device.firmware;
  const rbUpgrade =
    device.routerboard_available &&
    device.routerboard_current &&
    device.routerboard_available !== device.routerboard_current;

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
      <td className="px-4 py-3 font-mono text-xs">
        {device.firmware ?? "—"}
        {osUpgrade && (
          <span className="ml-1.5 rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
            → {device.firmware_available}
          </span>
        )}
        {rbUpgrade && (
          <span className="ml-1.5 rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
            RB → {device.routerboard_available}
          </span>
        )}
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

  const [created, setCreated] = useState<Device | null>(null);

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
    onSuccess: (d) => {
      // Don't dismiss the form yet — show the onboarding script first so
      // the operator can paste it into WinBox while still on this page.
      setCreated(d);
    },
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    m.mutate();
  }

  if (created) {
    return (
      <OnboardingPanel
        deviceId={created.id}
        deviceName={created.name}
        onClose={() => {
          setCreated(null);
          onCreated();
        }}
      />
    );
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
        <Field label="Site" htmlFor="d-site" hint="grouped by tenant">
          <select
            id="d-site"
            required
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
            className={inputClass}
          >
            {Object.entries(
              sites.reduce<Record<string, Site[]>>((acc, s) => {
                const key = s.tenant_name ?? "(no tenant)";
                (acc[key] ||= []).push(s);
                return acc;
              }, {}),
            ).map(([tenantName, list]) => (
              <optgroup key={tenantName} label={tenantName}>
                {list.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </optgroup>
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

function OnboardingPanel({
  deviceId,
  deviceName,
  onClose,
}: {
  deviceId: string;
  deviceName: string;
  onClose: () => void;
}) {
  const { data: script, isLoading, error } = useQuery<string>({
    queryKey: ["onboarding-script", deviceId],
    queryFn: () => getOnboardingScript(deviceId, { includePassword: true }),
  });
  const [copied, setCopied] = useState(false);

  return (
    <div className="mt-6 rounded-lg border border-emerald-300 bg-emerald-50/40 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-emerald-900">
            Device added — paste this into the router
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Open WinBox on <span className="font-medium">{deviceName}</span> → New
            Terminal → paste the whole script. It creates the management user,
            enables API + SSH, and adds the NetFleet IP to the whitelist. Safe
            to re-run.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent"
        >
          Done
        </button>
      </div>

      {isLoading && <p className="mt-4 text-sm text-muted-foreground">Generating…</p>}
      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      {script && (
        <>
          <div className="mt-4 flex items-center gap-2">
            <button
              type="button"
              onClick={async () => {
                await navigator.clipboard.writeText(script);
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1500);
              }}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
            >
              {copied ? "Copied!" : "Copy to clipboard"}
            </button>
            <a
              href={`/api/v1/devices/${deviceId}/onboarding-script`}
              download={`netfleet-onboarding-${deviceName}.rsc`}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              Download .rsc
            </a>
          </div>
          <pre className="mt-3 max-h-[40vh] overflow-auto rounded-md border border-border bg-zinc-950 p-3 font-mono text-[11px] text-zinc-100">
{script}
          </pre>
          <p className="mt-2 text-[11px] text-muted-foreground">
            The script needs your NetFleet external IP set in{" "}
            <Link
              href="/dashboard/settings"
              className="text-primary hover:underline"
            >
              Settings
            </Link>
            ; otherwise the whitelist line shows a placeholder you have to
            edit manually.
          </p>
        </>
      )}
    </div>
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

