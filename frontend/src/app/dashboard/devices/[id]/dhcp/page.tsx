"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";

import { useToast } from "@/components/toast";
import {
  createDhcpNetwork,
  createDhcpPool,
  createDhcpServer,
  deleteDhcpNetwork,
  deleteDhcpPool,
  deleteDhcpServer,
  deleteLease,
  listDhcpLeases,
  listDhcpNetworks,
  listDhcpPools,
  listDhcpServers,
  makeLeaseStatic,
  setLeaseComment,
  updateDhcpNetwork,
  updateDhcpPool,
  updateDhcpServer,
  type DhcpLease,
  type DhcpNetwork,
  type DhcpPool,
  type DhcpServer,
} from "@/lib/dhcp";

const TABS = [
  { id: "leases", label: "Leases" },
  { id: "servers", label: "Servers" },
  { id: "networks", label: "Networks" },
  { id: "pools", label: "Pools" },
] as const;

type Tab = (typeof TABS)[number]["id"];

function isTab(v: string | null): v is Tab {
  return v != null && TABS.some((t) => t.id === v);
}

export default function DhcpPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const raw = searchParams.get("tab");
  const tab: Tab = isTab(raw) ? raw : "leases";

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight">DHCP</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Pools, servers, networks and leases on this device. Changes apply to the
        router immediately.
      </p>

      <div className="mt-4 border-b border-border">
        <nav className="-mb-px flex flex-wrap gap-1">
          {TABS.map((t) => {
            const active = t.id === tab;
            return (
              <button
                key={t.id}
                onClick={() => router.replace(`${pathname}?tab=${t.id}`, { scroll: false })}
                className={
                  active
                    ? "border-b-2 border-primary px-3 py-2 text-sm font-medium text-primary"
                    : "border-b-2 border-transparent px-3 py-2 text-sm font-medium text-muted-foreground hover:border-border hover:text-foreground"
                }
              >
                {t.label}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="mt-6">
        {tab === "leases" && <LeasesPanel deviceId={deviceId} />}
        {tab === "servers" && <ServersPanel deviceId={deviceId} />}
        {tab === "networks" && <NetworksPanel deviceId={deviceId} />}
        {tab === "pools" && <PoolsPanel deviceId={deviceId} />}
      </div>
    </div>
  );
}

// ---------------- Leases ----------------

function LeasesPanel({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: leases, isLoading } = useQuery<DhcpLease[]>({
    queryKey: ["dhcp-leases", deviceId],
    queryFn: () => listDhcpLeases(deviceId),
  });

  const [filter, setFilter] = useState("");
  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (leases ?? []).filter((l) => {
      if (!needle) return true;
      const blob = [
        l.address,
        l.mac_address,
        l.host_name,
        l.comment,
        l.status,
        l.client_id,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return blob.includes(needle);
    });
  }, [leases, filter]);

  const make = useMutation({
    mutationFn: (id: string) => makeLeaseStatic(deviceId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dhcp-leases", deviceId] });
      toast.success("Lease reserved as static");
    },
    onError: (e: Error) => toast.error("Failed", e.message),
  });
  const del = useMutation({
    mutationFn: (id: string) => deleteLease(deviceId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dhcp-leases", deviceId] });
      toast.success("Lease deleted");
    },
    onError: (e: Error) => toast.error("Delete failed", e.message),
  });

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <input
          type="search"
          placeholder="Filter by IP / MAC / hostname / comment…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <span className="text-xs text-muted-foreground">
          {filtered.length} of {leases?.length ?? 0}
        </span>
      </div>

      {isLoading && (
        <p className="mt-4 text-sm text-muted-foreground">Loading…</p>
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Address</th>
              <th className="px-3 py-2 font-medium">MAC</th>
              <th className="px-3 py-2 font-medium">Host</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Server</th>
              <th className="px-3 py-2 font-medium">Comment</th>
              <th className="px-3 py-2 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filtered.map((l) => (
              <LeaseRow
                key={l.id ?? l.mac_address}
                lease={l}
                onMakeStatic={() => l.id && make.mutate(l.id)}
                onDelete={() => {
                  if (l.id && confirm(`Delete lease ${l.address}?`)) del.mutate(l.id);
                }}
                onSaveComment={async (text) => {
                  if (!l.id) return;
                  try {
                    await setLeaseComment(deviceId, l.id, text || null);
                    qc.invalidateQueries({ queryKey: ["dhcp-leases", deviceId] });
                    toast.success("Comment saved");
                  } catch (e) {
                    toast.error("Save failed", (e as Error).message);
                  }
                }}
              />
            ))}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-3 py-8 text-center text-muted-foreground"
                >
                  No leases match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function LeaseRow({
  lease,
  onMakeStatic,
  onDelete,
  onSaveComment,
}: {
  lease: DhcpLease;
  onMakeStatic: () => void;
  onDelete: () => void;
  onSaveComment: (text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(lease.comment ?? "");
  return (
    <tr className="align-top hover:bg-accent/30">
      <td className="px-3 py-2 font-mono text-xs">{lease.address}</td>
      <td className="px-3 py-2 font-mono text-xs">{lease.mac_address}</td>
      <td className="px-3 py-2 text-xs">{lease.host_name ?? "—"}</td>
      <td className="px-3 py-2 text-xs">
        <span
          className={`rounded-md px-1.5 py-0.5 ${
            lease.status === "bound"
              ? "bg-emerald-100 text-emerald-800"
              : "bg-zinc-100 text-zinc-800"
          }`}
        >
          {lease.status ?? "—"}
        </span>
        {lease.dynamic && (
          <span className="ml-1 rounded-md bg-amber-100 px-1.5 py-0.5 text-amber-900">
            dynamic
          </span>
        )}
        {lease.blocked && (
          <span className="ml-1 rounded-md bg-red-100 px-1.5 py-0.5 text-red-900">
            blocked
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-xs">{lease.server ?? "—"}</td>
      <td className="px-3 py-2 text-xs">
        {editing ? (
          <div className="flex items-center gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              type="button"
              onClick={() => {
                onSaveComment(text);
                setEditing(false);
              }}
              className="text-xs text-primary hover:underline"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setText(lease.comment ?? "");
                setEditing(false);
              }}
              className="text-xs text-muted-foreground hover:underline"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-left text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            {lease.comment || "+ add comment"}
          </button>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-right text-xs">
        {lease.dynamic && (
          <button
            type="button"
            onClick={onMakeStatic}
            className="mr-3 text-primary hover:underline"
          >
            Reserve (static)
          </button>
        )}
        <button
          type="button"
          onClick={onDelete}
          className="text-destructive hover:underline"
        >
          Delete
        </button>
      </td>
    </tr>
  );
}

// ---------------- Servers ----------------

function ServersPanel({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: servers, isLoading } = useQuery<DhcpServer[]>({
    queryKey: ["dhcp-servers", deviceId],
    queryFn: () => listDhcpServers(deviceId),
  });
  const { data: pools } = useQuery<DhcpPool[]>({
    queryKey: ["dhcp-pools", deviceId],
    queryFn: () => listDhcpPools(deviceId),
  });
  const [showForm, setShowForm] = useState(false);

  const del = useMutation({
    mutationFn: (id: string) => deleteDhcpServer(deviceId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dhcp-servers", deviceId] });
      toast.success("Server deleted");
    },
    onError: (e: Error) => toast.error("Delete failed", e.message),
  });

  return (
    <section>
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          One DHCP server per LAN interface. Bind it to a pool of leases.
        </p>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New server"}
        </button>
      </div>

      {showForm && (
        <ServerForm
          deviceId={deviceId}
          pools={pools ?? []}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["dhcp-servers", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Interface</th>
              <th className="px-3 py-2 font-medium">Pool</th>
              <th className="px-3 py-2 font-medium">Lease time</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (servers ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                  No servers yet.
                </td>
              </tr>
            )}
            {servers?.map((s) => (
              <tr key={s.id ?? s.name} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-medium">{s.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{s.interface}</td>
                <td className="px-3 py-2 text-xs">{s.address_pool ?? "—"}</td>
                <td className="px-3 py-2 text-xs">{s.lease_time ?? "—"}</td>
                <td className="px-3 py-2 text-xs">
                  {s.disabled ? (
                    <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 text-zinc-800">
                      disabled
                    </span>
                  ) : (
                    <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-emerald-800">
                      active
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right text-xs">
                  <button
                    onClick={() => {
                      if (s.id && confirm(`Delete server "${s.name}"?`)) del.mutate(s.id);
                    }}
                    className="text-destructive hover:underline"
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

function ServerForm({
  deviceId,
  pools,
  onCreated,
}: {
  deviceId: string;
  pools: DhcpPool[];
  onCreated: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [iface, setIface] = useState("");
  const [pool, setPool] = useState("");
  const [leaseTime, setLeaseTime] = useState("1d");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createDhcpServer(deviceId, {
        name,
        interface: iface,
        address_pool: pool || null,
        lease_time: leaseTime || null,
      }),
    onSuccess: () => {
      toast.success("Server created");
      onCreated();
    },
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
        <p className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block space-y-1 text-sm font-medium">
          Name
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="dhcp-lan"
          />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          Interface
          <input
            required
            value={iface}
            onChange={(e) => setIface(e.target.value)}
            className={`${input} font-mono`}
            placeholder="bridge-lan"
          />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          Address pool
          <select
            value={pool}
            onChange={(e) => setPool(e.target.value)}
            className={input}
          >
            <option value="">— none —</option>
            {pools.map((p) => (
              <option key={p.id ?? p.name} value={p.name}>
                {p.name} ({p.ranges})
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1 text-sm font-medium">
          Lease time
          <input
            value={leaseTime}
            onChange={(e) => setLeaseTime(e.target.value)}
            className={input}
            placeholder="1d, 30m, 12h"
          />
        </label>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create server"}
        </button>
      </div>
    </form>
  );
}

// ---------------- Networks ----------------

function NetworksPanel({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: networks, isLoading } = useQuery<DhcpNetwork[]>({
    queryKey: ["dhcp-networks", deviceId],
    queryFn: () => listDhcpNetworks(deviceId),
  });
  const [showForm, setShowForm] = useState(false);

  const del = useMutation({
    mutationFn: (id: string) => deleteDhcpNetwork(deviceId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dhcp-networks", deviceId] });
      toast.success("Network deleted");
    },
    onError: (e: Error) => toast.error("Delete failed", e.message),
  });

  return (
    <section>
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Per-subnet DHCP options: gateway, DNS, NTP, domain. Apply to leases
          inside the address range.
        </p>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New network"}
        </button>
      </div>

      {showForm && (
        <NetworkForm
          deviceId={deviceId}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["dhcp-networks", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Address</th>
              <th className="px-3 py-2 font-medium">Gateway</th>
              <th className="px-3 py-2 font-medium">DNS</th>
              <th className="px-3 py-2 font-medium">NTP</th>
              <th className="px-3 py-2 font-medium">Domain</th>
              <th className="px-3 py-2 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (networks ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                  No networks defined.
                </td>
              </tr>
            )}
            {networks?.map((n) => (
              <tr key={n.id ?? n.address} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-mono text-xs">{n.address}</td>
                <td className="px-3 py-2 font-mono text-xs">{n.gateway ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{n.dns_servers ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{n.ntp_servers ?? "—"}</td>
                <td className="px-3 py-2 text-xs">{n.domain ?? "—"}</td>
                <td className="px-3 py-2 text-right text-xs">
                  <button
                    onClick={() => {
                      if (n.id && confirm(`Delete network ${n.address}?`)) del.mutate(n.id);
                    }}
                    className="text-destructive hover:underline"
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

function NetworkForm({
  deviceId,
  onCreated,
}: {
  deviceId: string;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [address, setAddress] = useState("");
  const [gateway, setGateway] = useState("");
  const [dns, setDns] = useState("1.1.1.1,8.8.8.8");
  const [ntp, setNtp] = useState("");
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createDhcpNetwork(deviceId, {
        address,
        gateway: gateway || null,
        dns_servers: dns || null,
        ntp_servers: ntp || null,
        domain: domain || null,
      }),
    onSuccess: () => {
      toast.success("Network created");
      onCreated();
    },
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
        <p className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block space-y-1 text-sm font-medium">
          Network (CIDR)
          <input
            required
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.0/24"
          />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          Gateway
          <input
            value={gateway}
            onChange={(e) => setGateway(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.1"
          />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          DNS servers
          <input
            value={dns}
            onChange={(e) => setDns(e.target.value)}
            className={`${input} font-mono`}
          />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          NTP servers
          <input
            value={ntp}
            onChange={(e) => setNtp(e.target.value)}
            className={`${input} font-mono`}
            placeholder="pool.ntp.org"
          />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          Domain
          <input
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            className={input}
            placeholder="corp.local"
          />
        </label>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create network"}
        </button>
      </div>
    </form>
  );
}

// ---------------- Pools ----------------

function PoolsPanel({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: pools, isLoading } = useQuery<DhcpPool[]>({
    queryKey: ["dhcp-pools", deviceId],
    queryFn: () => listDhcpPools(deviceId),
  });
  const [showForm, setShowForm] = useState(false);

  const del = useMutation({
    mutationFn: (id: string) => deleteDhcpPool(deviceId, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dhcp-pools", deviceId] });
      toast.success("Pool deleted");
    },
    onError: (e: Error) => toast.error("Delete failed", e.message),
  });

  return (
    <section>
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          IP address ranges available to DHCP servers. Servers reference a pool
          by name.
        </p>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New pool"}
        </button>
      </div>

      {showForm && (
        <PoolForm
          deviceId={deviceId}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["dhcp-pools", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Ranges</th>
              <th className="px-3 py-2 font-medium">Next pool</th>
              <th className="px-3 py-2 font-medium">Comment</th>
              <th className="px-3 py-2 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (pools ?? []).length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">
                  No pools defined.
                </td>
              </tr>
            )}
            {pools?.map((p) => (
              <tr key={p.id ?? p.name} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-medium">{p.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{p.ranges}</td>
                <td className="px-3 py-2 font-mono text-xs">{p.next_pool ?? "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {p.comment ?? "—"}
                </td>
                <td className="px-3 py-2 text-right text-xs">
                  <button
                    onClick={() => {
                      if (p.id && confirm(`Delete pool "${p.name}"?`)) del.mutate(p.id);
                    }}
                    className="text-destructive hover:underline"
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

function PoolForm({
  deviceId,
  onCreated,
}: {
  deviceId: string;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [ranges, setRanges] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createDhcpPool(deviceId, {
        name,
        ranges,
        comment: comment || null,
      }),
    onSuccess: () => {
      toast.success("Pool created");
      onCreated();
    },
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
        <p className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-3">
        <label className="block space-y-1 text-sm font-medium">
          Name
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="lan-pool"
          />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          Ranges
          <input
            required
            value={ranges}
            onChange={(e) => setRanges(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.10-10.0.0.250"
          />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          Comment
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={input}
          />
        </label>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create pool"}
        </button>
      </div>
    </form>
  );
}

// Silence unused-import warnings until the edit forms come online.
void updateDhcpNetwork;
void updateDhcpPool;
void updateDhcpServer;

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
