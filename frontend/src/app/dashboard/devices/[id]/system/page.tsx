"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import {
  createSnmpCommunity,
  deleteSnmpCommunity,
  getNtp,
  getSnmp,
  listSnmpCommunities,
  updateNtp,
  updateSnmp,
  type NtpClient,
  type SnmpCommunity,
  type SnmpSettings,
} from "@/lib/router-system";

export default function SystemPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;

  return (
    <div className="space-y-10">
      <NtpSection deviceId={deviceId} />
      <SnmpSection deviceId={deviceId} />
      <SnmpCommunitiesSection deviceId={deviceId} />
    </div>
  );
}

// ---------------- NTP ----------------

function NtpSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery<NtpClient>({
    queryKey: ["ntp", deviceId],
    queryFn: () => getNtp(deviceId),
  });

  const [enabled, setEnabled] = useState(true);
  const [mode, setMode] = useState("unicast");
  const [servers, setServers] = useState("");
  const [done, setDone] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setEnabled(data.enabled);
      setMode(data.mode || "unicast");
      setServers(data.servers || [data.primary, data.secondary].filter(Boolean).join(","));
    }
  }, [data]);

  const m = useMutation({
    mutationFn: () =>
      updateNtp(deviceId, {
        enabled,
        mode: mode as "unicast" | "broadcast" | "multicast" | "manycast",
        servers: servers || null,
      }),
    onSuccess: () => {
      setDone(true);
      qc.invalidateQueries({ queryKey: ["ntp", deviceId] });
      setTimeout(() => setDone(false), 3000);
    },
    onError: (e: Error) => setErrMsg(e.message),
  });

  return (
    <section>
      <h2 className="text-lg font-semibold">NTP client</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Keep router clocks in sync — required for accurate logs, certificates and audit timestamps.
      </p>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}
      {errMsg && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errMsg}
        </div>
      )}
      {done && (
        <div className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          NTP settings updated.
        </div>
      )}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setErrMsg(null);
          m.mutate();
        }}
        className="mt-4 rounded-lg border border-border bg-card p-5"
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="size-4 rounded"
            disabled={isLoading}
          />
          NTP client enabled
        </label>

        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <Field label="Mode" htmlFor="n-mode">
            <select
              id="n-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className={input}
              disabled={isLoading || !enabled}
            >
              <option value="unicast">unicast</option>
              <option value="broadcast">broadcast</option>
              <option value="multicast">multicast</option>
              <option value="manycast">manycast</option>
            </select>
          </Field>
          <Field label="Servers (comma-separated DNS / IPs)" htmlFor="n-srv">
            <input
              id="n-srv"
              value={servers}
              onChange={(e) => setServers(e.target.value)}
              className={`${input} font-mono`}
              placeholder="0.pool.ntp.org,1.pool.ntp.org,time.google.com"
              disabled={isLoading || !enabled}
            />
          </Field>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="submit"
            disabled={m.isPending || isLoading}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Saving…" : "Save NTP settings"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- SNMP ----------------

function SnmpSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<SnmpSettings>({
    queryKey: ["snmp", deviceId],
    queryFn: () => getSnmp(deviceId),
  });

  const [enabled, setEnabled] = useState(false);
  const [contact, setContact] = useState("");
  const [location, setLocation] = useState("");
  const [trapTarget, setTrapTarget] = useState("");
  const [trapVersion, setTrapVersion] = useState<"1" | "2" | "3">("2");
  const [done, setDone] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setEnabled(data.enabled);
      setContact(data.contact ?? "");
      setLocation(data.location ?? "");
      setTrapTarget(data.trap_target ?? "");
      if (data.trap_version === "1" || data.trap_version === "2" || data.trap_version === "3") {
        setTrapVersion(data.trap_version);
      }
    }
  }, [data]);

  const m = useMutation({
    mutationFn: () =>
      updateSnmp(deviceId, {
        enabled,
        contact: contact || null,
        location: location || null,
        trap_target: trapTarget || null,
        trap_version: trapVersion,
      }),
    onSuccess: () => {
      setDone(true);
      qc.invalidateQueries({ queryKey: ["snmp", deviceId] });
      setTimeout(() => setDone(false), 3000);
    },
    onError: (e: Error) => setErrMsg(e.message),
  });

  return (
    <section>
      <h2 className="text-lg font-semibold">SNMP</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Enable SNMP for monitoring (read-only) or for control (read-write — be careful).
        Configure at least one community below to actually allow polling.
      </p>

      {errMsg && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errMsg}
        </div>
      )}
      {done && (
        <div className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          SNMP settings updated.
        </div>
      )}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setErrMsg(null);
          m.mutate();
        }}
        className="mt-4 rounded-lg border border-border bg-card p-5"
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="size-4 rounded"
            disabled={isLoading}
          />
          SNMP service enabled
        </label>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Contact" htmlFor="s-c">
            <input
              id="s-c"
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              className={input}
              placeholder="noc@itconnectge.ge"
              disabled={isLoading || !enabled}
            />
          </Field>
          <Field label="Location" htmlFor="s-l">
            <input
              id="s-l"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className={input}
              placeholder="Client A, server room 1"
              disabled={isLoading || !enabled}
            />
          </Field>
          <Field label="Trap target" htmlFor="s-tt" hint="ip[:port], comma-separated">
            <input
              id="s-tt"
              value={trapTarget}
              onChange={(e) => setTrapTarget(e.target.value)}
              className={`${input} font-mono`}
              placeholder="10.0.0.5:162"
              disabled={isLoading || !enabled}
            />
          </Field>
          <Field label="Trap version" htmlFor="s-tv">
            <select
              id="s-tv"
              value={trapVersion}
              onChange={(e) => setTrapVersion(e.target.value as "1" | "2" | "3")}
              className={input}
              disabled={isLoading || !enabled}
            >
              <option value="1">v1</option>
              <option value="2">v2c</option>
              <option value="3">v3</option>
            </select>
          </Field>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="submit"
            disabled={m.isPending || isLoading}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Saving…" : "Save SNMP settings"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- SNMP communities ----------------

function SnmpCommunitiesSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data: items, isLoading } = useQuery<SnmpCommunity[]>({
    queryKey: ["snmp-communities", deviceId],
    queryFn: () => listSnmpCommunities(deviceId),
  });

  const [showForm, setShowForm] = useState(false);
  const del = useMutation({
    mutationFn: (id: string) => deleteSnmpCommunity(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["snmp-communities", deviceId] }),
  });

  return (
    <section>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">SNMP communities</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Per-community access. Default <code>public</code> is read-only. Add a write community
            only if you really need it.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New community"}
        </button>
      </div>

      {showForm && (
        <CommunityForm
          deviceId={deviceId}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["snmp-communities", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Allowed from</th>
              <th className="px-4 py-2.5 font-medium">Read</th>
              <th className="px-4 py-2.5 font-medium">Write</th>
              <th className="px-4 py-2.5 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-5 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (!items || items.length === 0) && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  No SNMP communities defined.
                </td>
              </tr>
            )}
            {items?.map((c) => (
              <tr key={c.id ?? c.name} className="hover:bg-accent/30">
                <td className="px-4 py-2.5 font-medium">
                  {c.name}
                  {c.disabled && (
                    <span className="ml-2 rounded-md bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-800">
                      disabled
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 font-mono text-xs">{c.addresses ?? "any"}</td>
                <td className="px-4 py-2.5 text-xs">
                  {c.read_access ? (
                    <span className="text-emerald-700">✓</span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-xs">
                  {c.write_access ? (
                    <span className="text-amber-700">⚠ write</span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <button
                    onClick={() => {
                      if (c.id && confirm(`Delete SNMP community "${c.name}"?`)) {
                        del.mutate(c.id);
                      }
                    }}
                    className="text-xs text-destructive hover:underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CommunityForm({
  deviceId,
  onCreated,
}: {
  deviceId: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [addresses, setAddresses] = useState("");
  const [readAccess, setReadAccess] = useState(true);
  const [writeAccess, setWriteAccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createSnmpCommunity(deviceId, {
        name,
        addresses: addresses || null,
        read_access: readAccess,
        write_access: writeAccess,
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        setError(null);
        m.mutate();
      }}
      className="mt-4 rounded-lg border border-border bg-card p-5"
    >
      {error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Name" htmlFor="c-n">
          <input
            id="c-n"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="public"
          />
        </Field>
        <Field
          label="Allowed source addresses"
          htmlFor="c-a"
          hint="e.g. 10.0.0.0/24, blank = anywhere"
        >
          <input
            id="c-a"
            value={addresses}
            onChange={(e) => setAddresses(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.0/24,192.168.1.5"
          />
        </Field>
      </div>
      <div className="mt-4 flex items-center gap-6 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={readAccess}
            onChange={(e) => setReadAccess(e.target.checked)}
            className="size-4 rounded"
          />
          Read access
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={writeAccess}
            onChange={(e) => setWriteAccess(e.target.checked)}
            className="size-4 rounded"
          />
          <span>Write access <span className="text-xs text-amber-700">(dangerous)</span></span>
        </label>
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create community"}
        </button>
      </div>
    </form>
  );
}

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

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";
