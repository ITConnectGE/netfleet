"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { useToast } from "@/components/toast";
import { downloadAuthed } from "@/lib/api";
import {
  createDevice,
  getOnboardingScript,
  SERVER_VENDORS,
  testDeviceConnection,
  type Device,
} from "@/lib/devices";
import { listDrivers, type Driver } from "@/lib/drivers";
import {
  createSite,
  listSites,
  type Site,
  type SiteCreate,
} from "@/lib/sites";
import {
  createTenant,
  listTenants,
  type Tenant,
  type TenantCreate,
} from "@/lib/tenants";

const SiteLocationPicker = dynamic(
  () => import("@/components/site-location-picker"),
  { ssr: false, loading: () => <div className="h-72 animate-pulse rounded-md bg-muted" /> },
);

type Step = "tenant" | "site" | "device" | "onboarding";

function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

export default function FleetWizardPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("tenant");
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [site, setSite] = useState<Site | null>(null);
  const [device, setDevice] = useState<Device | null>(null);

  return (
    <div>
      <Link
        href="/dashboard/fleet"
        className="text-xs text-muted-foreground hover:underline"
      >
        ← Fleet
      </Link>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">
        Add to fleet
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Pick or create a tenant and site, register the device, then paste the
        onboarding script into the router.
      </p>

      <ProgressBar step={step} tenant={tenant} site={site} device={device} />

      <div className="mt-6">
        {step === "tenant" && (
          <TenantStep
            currentTenant={tenant}
            onPicked={(t) => {
              setTenant(t);
              setSite(null);
              setStep("site");
            }}
          />
        )}
        {step === "site" && tenant && (
          <SiteStep
            tenant={tenant}
            currentSite={site}
            onBack={() => setStep("tenant")}
            onPicked={(s) => {
              setSite(s);
              setStep("device");
            }}
          />
        )}
        {step === "device" && site && (
          <DeviceStep
            site={site}
            onBack={() => setStep("site")}
            onCreated={(d) => {
              setDevice(d);
              setStep("onboarding");
            }}
          />
        )}
        {step === "onboarding" && device && (
          <OnboardingStep
            device={device}
            onDone={() => router.push(`/dashboard/devices/${device.id}`)}
          />
        )}
      </div>
    </div>
  );
}

// ---------------- Progress ----------------

function ProgressBar({
  step,
  tenant,
  site,
  device,
}: {
  step: Step;
  tenant: Tenant | null;
  site: Site | null;
  device: Device | null;
}) {
  const steps: { id: Step; label: string; done: boolean }[] = [
    { id: "tenant", label: "Tenant", done: tenant !== null },
    { id: "site", label: "Site", done: site !== null },
    { id: "device", label: "Device", done: device !== null },
    { id: "onboarding", label: "Onboarding", done: false },
  ];
  return (
    <ol className="mt-6 flex flex-wrap gap-1 text-xs">
      {steps.map((s, i) => {
        const active = s.id === step;
        return (
          <li
            key={s.id}
            className={`flex items-center gap-1 rounded-md px-2.5 py-1 ${
              active
                ? "bg-primary/10 text-primary"
                : s.done
                  ? "bg-muted text-muted-foreground"
                  : "bg-muted/40 text-muted-foreground"
            }`}
          >
            <span className="font-mono">{i + 1}</span> · {s.label}
            {s.done && !active && <span>✓</span>}
          </li>
        );
      })}
    </ol>
  );
}

// ---------------- Step 1: Tenant ----------------

function TenantStep({
  currentTenant,
  onPicked,
}: {
  currentTenant: Tenant | null;
  onPicked: (t: Tenant) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: tenants } = useQuery<Tenant[]>({
    queryKey: ["tenants"],
    queryFn: listTenants,
  });

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (): Promise<Tenant> => {
      const payload: TenantCreate = {
        name,
        slug: slugify(name) || "tenant",
      };
      return createTenant(payload);
    },
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      toast.success("Tenant created", t.name);
      onPicked(t);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-base font-semibold">Pick a tenant</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        A tenant is usually a customer or business unit. Devices belong to a
        site, sites belong to a tenant.
      </p>

      <div className="mt-4 space-y-2">
        {tenants?.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onPicked(t)}
            className={`block w-full rounded-md border px-3 py-2 text-left text-sm transition hover:bg-accent ${
              currentTenant?.id === t.id
                ? "border-primary bg-primary/5"
                : "border-input bg-background"
            }`}
          >
            <div className="font-medium">{t.name}</div>
            <div className="text-[11px] text-muted-foreground">
              {t.site_count} site{t.site_count === 1 ? "" : "s"} ·{" "}
              {t.device_count} device{t.device_count === 1 ? "" : "s"}
            </div>
          </button>
        ))}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        {creating ? (
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              setError(null);
              if (!name.trim()) {
                setError("Name is required.");
                return;
              }
              create.mutate();
            }}
            className="space-y-3"
          >
            {error && (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </p>
            )}
            <label className="block space-y-1 text-sm font-medium">
              New tenant name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="Acme Manufacturing"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCreating(false)}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={create.isPending}
                className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {create.isPending ? "Creating…" : "Create + continue"}
              </button>
            </div>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="text-sm text-primary hover:underline"
          >
            + Create a new tenant instead
          </button>
        )}
      </div>
    </section>
  );
}

// ---------------- Step 2: Site ----------------

function SiteStep({
  tenant,
  currentSite,
  onBack,
  onPicked,
}: {
  tenant: Tenant;
  currentSite: Site | null;
  onBack: () => void;
  onPicked: (s: Site) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites", tenant.id],
    queryFn: () => listSites(tenant.id),
  });

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (): Promise<Site> => {
      const payload: SiteCreate = {
        tenant_id: tenant.id,
        name,
        slug: slugify(name) || "site",
        address: address || null,
        latitude: coords?.lat ?? null,
        longitude: coords?.lon ?? null,
      };
      return createSite(payload);
    },
    onSuccess: (s) => {
      qc.invalidateQueries({ queryKey: ["sites", tenant.id] });
      qc.invalidateQueries({ queryKey: ["sites"] });
      toast.success("Site created", s.name);
      onPicked(s);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold">
            Pick a site in <span className="font-mono">{tenant.name}</span>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Sites are physical or logical locations under the tenant.
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="text-xs text-muted-foreground hover:underline"
        >
          ← Tenant
        </button>
      </div>

      <div className="mt-4 space-y-2">
        {sites?.length === 0 && !creating && (
          <p className="rounded-md border border-dashed border-border bg-background p-3 text-center text-xs text-muted-foreground">
            No sites under {tenant.name} yet.
          </p>
        )}
        {sites?.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => onPicked(s)}
            className={`block w-full rounded-md border px-3 py-2 text-left text-sm transition hover:bg-accent ${
              currentSite?.id === s.id
                ? "border-primary bg-primary/5"
                : "border-input bg-background"
            }`}
          >
            <div className="font-medium">{s.name}</div>
            <div className="text-[11px] text-muted-foreground">
              {s.address ?? "no address"} · {s.device_count} device
              {s.device_count === 1 ? "" : "s"}
            </div>
          </button>
        ))}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        {creating ? (
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              setError(null);
              if (!name.trim()) {
                setError("Name is required.");
                return;
              }
              create.mutate();
            }}
            className="space-y-3"
          >
            {error && (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </p>
            )}
            <label className="block space-y-1 text-sm font-medium">
              New site name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="Head office"
              />
            </label>
            <label className="block space-y-1 text-sm font-medium">
              Address{" "}
              <span className="text-xs font-normal text-muted-foreground">
                (optional)
              </span>
              <input
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="123 Rustaveli Ave, Tbilisi"
              />
            </label>
            <div className="text-xs font-medium text-muted-foreground">
              Location (optional)
            </div>
            <SiteLocationPicker
              address={address}
              latitude={coords?.lat ?? null}
              longitude={coords?.lon ?? null}
              onChange={(lat, lon) => setCoords({ lat, lon })}
              onAddressChange={(addr) => setAddress(addr)}
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCreating(false)}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={create.isPending}
                className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {create.isPending ? "Creating…" : "Create + continue"}
              </button>
            </div>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="text-sm text-primary hover:underline"
          >
            + Create a new site instead
          </button>
        )}
      </div>
    </section>
  );
}

// ---------------- Step 3: Device ----------------

function DeviceStep({
  site,
  onBack,
  onCreated,
}: {
  site: Site;
  onBack: () => void;
  onCreated: (d: Device) => void;
}) {
  const { data: drivers } = useQuery<Driver[]>({
    queryKey: ["drivers"],
    queryFn: listDrivers,
  });
  const [name, setName] = useState("");
  const [vendor, setVendor] = useState("mikrotik");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(8728);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [verifyTls, setVerifyTls] = useState(false);
  const [useSudo, setUseSudo] = useState(true);
  const [sshAuth, setSshAuth] = useState<"generate" | "password">("generate");
  const [error, setError] = useState<string | null>(null);

  const isServer = SERVER_VENDORS.has(vendor);

  useEffect(() => {
    if (!drivers || drivers.length === 0) return;
    if (!drivers.find((d) => d.vendor === vendor)) {
      setVendor(drivers[0].vendor);
    }
  }, [drivers, vendor]);

  // Switching vendor rewrites the port and the default account, because a
  // RouterOS 'admin' on 8728 and a Linux 'netfleet' on 22 share nothing.
  useEffect(() => {
    if (SERVER_VENDORS.has(vendor)) {
      setPort(22);
      setUsername((u) => (u === "admin" ? "netfleet" : u));
    } else if (vendor === "mikrotik") {
      setPort(8728);
      setUsername((u) => (u === "netfleet" ? "admin" : u));
    }
  }, [vendor]);

  const m = useMutation({
    mutationFn: () =>
      createDevice(
        isServer
          ? {
              site_id: site.id,
              name,
              vendor,
              host,
              // The backend keeps port and ssh_port in step for servers;
              // sending both avoids depending on that as a side effect.
              port,
              ssh_port: port,
              transport: "ssh",
              username,
              password: sshAuth === "password" ? password || null : null,
              generate_ssh_key: sshAuth === "generate",
              become_method: useSudo ? "sudo" : "none",
            }
          : {
              site_id: site.id,
              name,
              vendor,
              host,
              port,
              username,
              password: password || null,
              verify_tls: verifyTls,
            },
      ),
    onSuccess: (d) => onCreated(d),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold">
            Add a device to <span className="font-mono">{site.name}</span>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Credentials are encrypted at rest. The next step gives you a
            ready-made script for the device.
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="text-xs text-muted-foreground hover:underline"
        >
          ← Site
        </button>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          m.mutate();
        }}
        className="mt-4 space-y-3"
      >
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block space-y-1 text-sm font-medium">
            Display name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={input}
              placeholder="Office CCR"
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Vendor
            <select
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
              className={input}
            >
              {(drivers ?? []).map((d) => (
                <option key={d.vendor} value={d.vendor}>
                  {d.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Host
            <input
              required
              value={host}
              onChange={(e) => setHost(e.target.value)}
              className={`${input} font-mono`}
              placeholder="192.0.2.10"
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Port
            <input
              type="number"
              min={1}
              max={65535}
              value={port}
              onChange={(e) => setPort(Number(e.target.value))}
              className={input}
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Username
            <input
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="off"
              className={input}
            />
            {isServer && (
              <span className="block text-xs font-normal text-muted-foreground">
                The onboarding script creates this account on the server.
              </span>
            )}
          </label>
          {isServer ? (
            <label className="block space-y-1 text-sm font-medium">
              Authentication
              <select
                value={sshAuth}
                onChange={(e) =>
                  setSshAuth(e.target.value as "generate" | "password")
                }
                className={input}
              >
                <option value="generate">Generate SSH key (recommended)</option>
                <option value="password">Password</option>
              </select>
              <span className="block text-xs font-normal text-muted-foreground">
                {sshAuth === "generate"
                  ? "NetFleet creates the keypair. The public half goes into the onboarding script; the private half never leaves this server."
                  : "Password auth is weaker and many cloud images disable it by default."}
              </span>
            </label>
          ) : (
            <label className="block space-y-1 text-sm font-medium">
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                className={input}
              />
            </label>
          )}
          {isServer && sshAuth === "password" && (
            <label className="block space-y-1 text-sm font-medium">
              Password
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                className={input}
              />
            </label>
          )}
        </div>
        {isServer ? (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useSudo}
              onChange={(e) => setUseSudo(e.target.checked)}
              className="size-4 rounded"
            />
            Escalate with sudo (uncheck only when connecting directly as root)
          </label>
        ) : (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={verifyTls}
              onChange={(e) => setVerifyTls(e.target.checked)}
              className="size-4 rounded"
            />
            Reject untrusted TLS certificates
          </label>
        )}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={m.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Adding…" : "Add device + continue"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- Step 4: Onboarding ----------------

function OnboardingStep({
  device,
  onDone,
}: {
  device: Device;
  onDone: () => void;
}) {
  const toast = useToast();
  const { data: script, isLoading, error } = useQuery<string>({
    queryKey: ["onboarding-script", device.id],
    queryFn: () => getOnboardingScript(device.id, { includePassword: true }),
  });
  const [copied, setCopied] = useState(false);

  const safeName = useMemo(
    () => device.name.replace(/[^a-z0-9-]+/gi, "-").toLowerCase(),
    [device.name],
  );
  const isServer = device.device_class === "server";
  const ext = isServer ? "sh" : "rsc";

  // For SSH devices this is not just a convenience: the first successful
  // test is what pins the host key, and every other endpoint refuses to
  // talk to an unpinned device. Running it here means the operator leaves
  // the wizard with a verified host rather than a 409 on the next page.
  const test = useMutation({
    mutationFn: () => testDeviceConnection(device.id),
    onSuccess: (r) =>
      r.ok
        ? toast.success("Connected", `${r.identity ?? device.name} is online`)
        : toast.error("Not connected yet", r.error ?? "unknown error"),
    onError: (e: Error) => toast.error("Test failed", e.message),
  });

  return (
    <section className="rounded-lg border border-emerald-300 bg-emerald-50/40 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-emerald-900">
            Device added — finish onboarding
          </h2>
          {isServer ? (
            <p className="mt-1 text-sm text-muted-foreground">
              Copy this script onto{" "}
              <span className="font-medium">{device.name}</span> and run{" "}
              <code className="rounded bg-black/10 px-1 font-mono text-xs">
                sudo bash netfleet-onboarding-{safeName}.sh
              </code>
              , then click <span className="font-medium">Open device</span> below
              to watch the first connection turn green. It is safe to re-run.
            </p>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">
              Open WinBox / SSH on <span className="font-medium">{device.name}</span>,
              paste the script (or upload the .rsc), then click&nbsp;
              <span className="font-medium">Open device</span> below to watch the
              first connection turn green.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onDone}
          className="shrink-0 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Open device →
        </button>
      </div>

      {isLoading && (
        <p className="mt-4 text-sm text-muted-foreground">Generating…</p>
      )}
      {error && (
        <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </p>
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
            <button
              type="button"
              onClick={() =>
                downloadAuthed(
                  `/api/v1/devices/${device.id}/onboarding-script`,
                  `netfleet-onboarding-${safeName}.${ext}`,
                ).catch((e: Error) => toast.error("Download failed", e.message))
              }
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
            >
              Download .{ext}
            </button>
            <button
              type="button"
              onClick={() => test.mutate()}
              disabled={test.isPending}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
              title={
                isServer
                  ? "Run this after the script. The first successful connection pins the server's SSH host key."
                  : "Check that NetFleet can reach the device"
              }
            >
              {test.isPending ? "Testing…" : "Test connection"}
            </button>
          </div>
          {isServer && (
            <p className="mt-2 text-xs text-muted-foreground">
              Run <span className="font-medium">Test connection</span> once the
              script has finished. It pins this server&apos;s SSH host key —
              until then NetFleet refuses to run anything else against it, and
              afterwards a changed host key fails loudly instead of being
              accepted silently.
            </p>
          )}
          <pre className="mt-3 max-h-[40vh] overflow-auto rounded-md border border-border bg-zinc-950 p-3 font-mono text-[11px] text-zinc-100">
            {script}
          </pre>
        </>
      )}
    </section>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";
