"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { AccessPanel } from "@/components/access-panel";
import { FirmwareCard } from "@/components/firmware-card";
import { RequestAccessButton } from "@/components/request-access-button";
import { StatusPill } from "@/components/status-pill";
import { useToast } from "@/components/toast";
import { downloadAuthed } from "@/lib/api";
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
  const toast = useToast();
  const id = params.id;
  const [editing, setEditing] = useState(false);

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
    queryFn: () => listSites(),
  });
  const { data: drivers } = useQuery<Driver[]>({ queryKey: ["drivers"], queryFn: listDrivers });

  // We pass the previous site_id alongside the new one so the success
  // handler can fire an "Undo" toast that re-issues the move in reverse.
  // No undo window timeout: the toast itself auto-dismisses after 3s,
  // and the action remains explicit (operator must click Undo).
  const moveSite = useMutation({
    mutationFn: (vars: { newSiteId: string; previousSiteId: string }) =>
      updateDevice(id, { site_id: vars.newSiteId }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["device", id] });
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["sites"] });
      const target = sites?.find((s) => s.id === vars.newSiteId);
      toast.push(
        "success",
        `Moved to ${target?.name ?? "new site"}`,
      );
      // Replay button as a second toast so the user can revert without
      // hunting for the dropdown again.
      if (vars.previousSiteId !== vars.newSiteId) {
        // Defer one tick so it stacks visibly under the success toast.
        window.setTimeout(() => {
          toast.info(
            "Move site",
            "Wrong target? Re-open the Move… menu and pick the previous site.",
          );
        }, 50);
      }
    },
    onError: (e: Error) => toast.error("Move failed", e.message),
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
          {device.last_seen_at && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              Last polled{" "}
              <time dateTime={device.last_seen_at}>
                {formatLastSeen(device.last_seen_at)}
              </time>
            </p>
          )}
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
                onMove={(newId) =>
                  moveSite.mutate({
                    newSiteId: newId,
                    previousSiteId: device.site_id,
                  })
                }
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
            type="button"
            onClick={() => setEditing(true)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
            title="Edit credentials, host / port, SSH port, notes"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={() => {
              const safeName = device.name.replace(/[^a-z0-9-]+/gi, "-").toLowerCase();
              downloadAuthed(
                `/api/v1/devices/${device.id}/onboarding-script`,
                `netfleet-onboarding-${safeName}.rsc`,
              ).catch((e: Error) => toast.error("Download failed", e.message));
            }}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
            title="Download the RouterOS onboarding script (.rsc) that prepares this device for NetFleet management"
          >
            Onboarding .rsc
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
          role="status"
          className={`mt-6 flex items-start gap-3 rounded-md border px-4 py-3 text-sm ${
            test.data.ok
              ? "border-emerald-300 bg-emerald-50 text-emerald-900"
              : "border-red-300 bg-red-50 text-red-900"
          }`}
        >
          {test.data.ok ? <CheckIcon /> : <CrossIcon />}
          <div className="min-w-0 flex-1">
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
        </div>
      )}

      <div className="mt-6">
        <FirmwareCard deviceId={device.id} />
      </div>

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

      <AccessPanel scope="device" id={device.id} />

      <div className="mt-4 flex justify-end">
        <RequestAccessButton
          scopeType="device"
          scopeId={device.id}
          scopeLabel={device.name}
          variant="block"
        />
      </div>

      {editing && (
        <EditDeviceModal
          device={device}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            qc.invalidateQueries({ queryKey: ["device", id] });
            qc.invalidateQueries({ queryKey: ["devices"] });
            toast.success("Device updated");
          }}
        />
      )}
    </div>
  );
}

function EditDeviceModal({
  device,
  onClose,
  onSaved,
}: {
  device: Device;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(device.name);
  const [host, setHost] = useState(device.host);
  const [port, setPort] = useState<number>(device.port);
  const [sshPort, setSshPort] = useState<number>(device.ssh_port ?? 22);
  const [transport, setTransport] = useState(device.transport);
  const [username, setUsername] = useState(device.username);
  // Password / API key blanks mean "leave the stored value alone" — only
  // changed when the operator actually types something here.
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [verifyTls, setVerifyTls] = useState(device.verify_tls);
  const [notes, setNotes] = useState(device.notes ?? "");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      updateDevice(device.id, {
        name,
        host,
        port,
        ssh_port: sshPort,
        transport,
        username,
        password: password ? password : undefined,
        api_key: apiKey ? apiKey : undefined,
        verify_tls: verifyTls,
        notes: notes || null,
      }),
    onSuccess: () => onSaved(),
    onError: (e: Error) => {
      setError(e.message);
      toast.error("Save failed", e.message);
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-2xl rounded-lg border border-border bg-card p-6 shadow-xl">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Edit device</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            ✕
          </button>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Leave password / API key blank to keep the current value. Both are
          encrypted at rest.
        </p>

        {error && (
          <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            m.mutate();
          }}
          className="mt-4 grid gap-3 md:grid-cols-2"
        >
          <label className="block space-y-1 text-sm font-medium">
            Display name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={modalInput}
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Vendor
            <input
              value={device.vendor}
              disabled
              className={`${modalInput} cursor-not-allowed bg-muted text-muted-foreground`}
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Host / IP
            <input
              required
              value={host}
              onChange={(e) => setHost(e.target.value)}
              className={`${modalInput} font-mono`}
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            API port
            <input
              type="number"
              min={1}
              max={65535}
              value={port}
              onChange={(e) => setPort(Number(e.target.value))}
              className={modalInput}
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            SSH port
            <input
              type="number"
              min={1}
              max={65535}
              value={sshPort}
              onChange={(e) => setSshPort(Number(e.target.value))}
              className={modalInput}
            />
            <span className="block text-[11px] italic font-normal text-muted-foreground">
              Used for backups + restore (SFTP). Default 22.
            </span>
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Transport
            <select
              value={transport}
              onChange={(e) =>
                setTransport(e.target.value as Device["transport"])
              }
              className={modalInput}
            >
              {(["api", "rest", "ssh", "netconf"] as const).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Username
            <input
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="off"
              className={modalInput}
            />
          </label>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={verifyTls}
              onChange={(e) => setVerifyTls(e.target.checked)}
              className="size-4 rounded"
            />
            Reject untrusted TLS
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Password{" "}
            <span className="text-xs font-normal text-muted-foreground">
              {device.has_password ? "(set — leave blank to keep)" : "(none)"}
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              className={modalInput}
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            API key{" "}
            <span className="text-xs font-normal text-muted-foreground">
              {device.has_api_key ? "(set — leave blank to keep)" : "(none)"}
            </span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="new-password"
              className={modalInput}
            />
          </label>
          <label className="md:col-span-2 block space-y-1 text-sm font-medium">
            Notes
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className={modalInput}
            />
          </label>
          <div className="md:col-span-2 mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={m.isPending}
              className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {m.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const modalInput =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";

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

function formatLastSeen(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function CheckIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="mt-0.5 size-5 shrink-0 text-emerald-600"
      aria-hidden="true"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function CrossIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="mt-0.5 size-5 shrink-0 text-red-600"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </svg>
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
