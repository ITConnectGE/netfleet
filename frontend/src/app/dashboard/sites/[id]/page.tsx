"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { listDevices, type Device } from "@/lib/devices";
import { deleteSite, getSite, updateSite, type Site, type SiteUpdate } from "@/lib/sites";

export default function SiteDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const id = params.id;

  const { data: site, isLoading } = useQuery<Site>({
    queryKey: ["site", id],
    queryFn: () => getSite(id),
    enabled: Boolean(id),
  });
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices", { siteId: id }],
    queryFn: () => listDevices(id),
    enabled: Boolean(id),
  });

  const del = useMutation({
    mutationFn: () => deleteSite(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sites"] });
      router.replace("/dashboard/sites");
    },
  });

  if (isLoading || !site) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div>
      <Link href="/dashboard/sites" className="text-xs text-muted-foreground hover:underline">
        ← Sites
      </Link>
      <div className="mt-1 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{site.name}</h1>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{site.slug}</p>
        </div>
        <button
          onClick={() => {
            if (site.device_count > 0) {
              alert(
                `Cannot delete: ${site.device_count} device(s) still attached. Move or delete them first.`,
              );
              return;
            }
            if (confirm(`Delete site "${site.name}"?`)) del.mutate();
          }}
          disabled={del.isPending}
          className="shrink-0 rounded-md border border-destructive/40 bg-background px-3 py-1.5 text-sm font-medium text-destructive transition hover:bg-destructive/10 disabled:opacity-50"
        >
          Delete site
        </button>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <SiteInfoCard site={site} />
        <SiteStatsCard site={site} devices={devices ?? []} />
      </div>

      <div className="mt-8 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Devices at this site</h2>
        <Link
          href="/dashboard/devices"
          className="text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          + add device (all devices)
        </Link>
      </div>

      <div className="mt-3 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Vendor</th>
              <th className="px-4 py-2.5 font-medium">Host</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium">Last seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {!devices || devices.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  No devices at this site yet.
                </td>
              </tr>
            ) : (
              devices.map((d) => (
                <tr key={d.id} className="hover:bg-accent/30">
                  <td className="px-4 py-3 font-medium">
                    <Link href={`/dashboard/devices/${d.id}`} className="hover:underline">
                      {d.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{d.vendor}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {d.host}:{d.port}
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill status={d.status} />
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : "never"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SiteInfoCard({ site }: { site: Site }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<SiteUpdate>({
    name: site.name,
    address: site.address,
    contact_email: site.contact_email,
    contact_phone: site.contact_phone,
    notes: site.notes,
  });
  const [error, setError] = useState<string | null>(null);

  // Sync draft when site refetches while not editing.
  useEffect(() => {
    if (!editing) {
      setDraft({
        name: site.name,
        address: site.address,
        contact_email: site.contact_email,
        contact_phone: site.contact_phone,
        notes: site.notes,
      });
    }
  }, [site, editing]);

  const m = useMutation({
    mutationFn: () =>
      updateSite(site.id, {
        name: draft.name,
        address: draft.address || null,
        contact_email: draft.contact_email || null,
        contact_phone: draft.contact_phone || null,
        notes: draft.notes || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["site", site.id] });
      qc.invalidateQueries({ queryKey: ["sites"] });
      setEditing(false);
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  if (!editing) {
    return (
      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">Info</h2>
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            Edit
          </button>
        </div>
        <dl className="mt-3 space-y-2 text-sm">
          <Row label="Address">{site.address ?? "—"}</Row>
          <Row label="Contact email">{site.contact_email ?? "—"}</Row>
          <Row label="Contact phone">{site.contact_phone ?? "—"}</Row>
          <Row label="Notes">
            <span className="whitespace-pre-wrap text-right">{site.notes ?? "—"}</span>
          </Row>
        </dl>
      </div>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        m.mutate();
      }}
      className="rounded-lg border border-border bg-card p-5"
    >
      <h2 className="text-sm font-medium text-muted-foreground">Edit info</h2>
      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}
      <div className="mt-3 space-y-3">
        <Field label="Name">
          <input
            required
            value={draft.name ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            className={inputClass}
          />
        </Field>
        <Field label="Address">
          <input
            value={draft.address ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, address: e.target.value }))}
            className={inputClass}
          />
        </Field>
        <Field label="Contact email">
          <input
            type="email"
            value={draft.contact_email ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, contact_email: e.target.value }))}
            className={inputClass}
          />
        </Field>
        <Field label="Contact phone">
          <input
            value={draft.contact_phone ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, contact_phone: e.target.value }))}
            className={inputClass}
          />
        </Field>
        <Field label="Notes">
          <textarea
            rows={3}
            value={draft.notes ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
            className={inputClass}
          />
        </Field>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={() => {
            setEditing(false);
            setError(null);
          }}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm transition hover:bg-accent"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function SiteStatsCard({ site, devices }: { site: Site; devices: Device[] }) {
  const online = devices.filter((d) => d.status === "online").length;
  const offline = devices.filter((d) => d.status === "offline").length;
  const errored = devices.filter((d) => d.status === "error").length;
  const unknown = devices.filter((d) => d.status === "unknown").length;
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-sm font-medium text-muted-foreground">Devices</h2>
      <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Total</dt>
        <dd className="text-right font-medium">{devices.length}</dd>
        <dt className="text-muted-foreground">Online</dt>
        <dd className="text-right text-emerald-700">{online}</dd>
        <dt className="text-muted-foreground">Offline</dt>
        <dd className="text-right text-zinc-700">{offline}</dd>
        <dt className="text-muted-foreground">Error</dt>
        <dd className="text-right text-red-700">{errored}</dd>
        <dt className="text-muted-foreground">Unknown</dt>
        <dd className="text-right text-zinc-500">{unknown}</dd>
        <dt className="text-muted-foreground">Created</dt>
        <dd className="text-right text-xs text-muted-foreground">
          {new Date(site.created_at).toLocaleDateString()}
        </dd>
      </dl>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
