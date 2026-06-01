"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

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

// ---------------- Shared table helpers ----------------

type SortDir = "asc" | "desc" | null;

interface SortState {
  by: string | null;
  dir: SortDir;
}

interface UseTableOpts<T> {
  rows: T[];
  /** Map column id → string accessor for filter + alphabetic sort. */
  accessors: Record<string, (row: T) => string>;
  /** Optional: map column id → numeric accessor; used for sort when present. */
  numericAccessors?: Record<string, (row: T) => number>;
}

function useTable<T>({ rows, accessors, numericAccessors }: UseTableOpts<T>) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<SortState>({ by: null, dir: null });

  const onFilter = (id: string, v: string) =>
    setFilters((p) => ({ ...p, [id]: v }));

  function onSort(id: string) {
    setSort((prev) => {
      if (prev.by !== id) return { by: id, dir: "asc" };
      if (prev.dir === "asc") return { by: id, dir: "desc" };
      return { by: null, dir: null };
    });
  }

  const visible = useMemo(() => {
    let out = rows.filter((r) =>
      Object.entries(filters).every(([id, q]) => {
        const needle = q.trim().toLowerCase();
        if (!needle) return true;
        const acc = accessors[id];
        if (!acc) return true;
        return acc(r).toLowerCase().includes(needle);
      }),
    );
    if (sort.by && sort.dir) {
      const numeric = numericAccessors?.[sort.by];
      const text = accessors[sort.by];
      out = [...out].sort((a, b) => {
        if (numeric) {
          return numeric(a) - numeric(b);
        }
        return text ? text(a).localeCompare(text(b)) : 0;
      });
      if (sort.dir === "desc") out.reverse();
    }
    return out;
  }, [rows, filters, sort, accessors, numericAccessors]);

  return { visible, filters, sort, onFilter, onSort };
}

interface ColDef {
  id: string;
  label: string;
  align?: "left" | "right";
  /** Hide the per-column filter input (e.g. for the actions column). */
  noFilter?: boolean;
  /** Disable click-to-sort (actions / non-sortable columns). */
  noSort?: boolean;
  /** Override the filter placeholder. */
  placeholder?: string;
}

function TableHeader({
  columns,
  sort,
  onSort,
  filters,
  onFilter,
}: {
  columns: ColDef[];
  sort: SortState;
  onSort: (id: string) => void;
  filters: Record<string, string>;
  onFilter: (id: string, value: string) => void;
}) {
  return (
    <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
      <tr>
        {columns.map((c) => {
          const isSorted = sort.by === c.id && sort.dir;
          const align = c.align === "right" ? "text-right" : "text-left";
          return (
            <th key={c.id} className={`px-3 py-2 font-medium ${align}`}>
              {c.noSort ? (
                <span>{c.label}</span>
              ) : (
                <button
                  type="button"
                  onClick={() => onSort(c.id)}
                  className="inline-flex items-center gap-1 hover:text-foreground"
                >
                  {c.label}
                  <span
                    className={
                      isSorted
                        ? "text-foreground"
                        : "text-muted-foreground/40"
                    }
                  >
                    {isSorted
                      ? sort.dir === "asc"
                        ? "▲"
                        : "▼"
                      : "⇅"}
                  </span>
                </button>
              )}
            </th>
          );
        })}
      </tr>
      <tr className="border-b border-border bg-muted/20">
        {columns.map((c) => (
          <th key={`${c.id}-f`} className="px-2 py-1 align-top">
            {c.noFilter ? null : (
              <input
                value={filters[c.id] ?? ""}
                onChange={(e) => onFilter(c.id, e.target.value)}
                placeholder={c.placeholder ?? "filter…"}
                aria-label={`Filter ${c.label}`}
                className="block w-full rounded border border-input bg-background px-2 py-0.5 text-[11px] font-normal text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring"
              />
            )}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function EmptyRow({
  span,
  isLoading,
  empty,
}: {
  span: number;
  isLoading: boolean;
  empty: string;
}) {
  return (
    <tr>
      <td
        colSpan={span}
        className="px-3 py-6 text-center text-muted-foreground"
      >
        {isLoading ? "Loading…" : empty}
      </td>
    </tr>
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

  const cols: ColDef[] = [
    { id: "address", label: "Address" },
    { id: "mac_address", label: "MAC" },
    { id: "host_name", label: "Host" },
    { id: "status", label: "Status" },
    { id: "server", label: "Server" },
    { id: "type", label: "Type", placeholder: "static / dynamic" },
    { id: "expires", label: "Expires", noFilter: false },
    { id: "comment", label: "Comment" },
    { id: "actions", label: "", align: "right", noFilter: true, noSort: true },
  ];

  const accessors: Record<string, (r: DhcpLease) => string> = {
    address: (r) => r.address,
    mac_address: (r) => r.mac_address,
    host_name: (r) => r.host_name ?? "",
    status: (r) => r.status ?? "",
    server: (r) => r.server ?? "",
    type: (r) => (r.dynamic ? "dynamic" : "static") + (r.blocked ? " blocked" : ""),
    expires: (r) => r.expires_at_iso ?? "",
    comment: (r) => r.comment ?? "",
    actions: () => "",
  };
  // Sort addresses as IPv4 numerically when possible, then alphabetically.
  const numericAccessors: Record<string, (r: DhcpLease) => number> = {
    address: (r) => ipToInt(r.address),
  };

  const { visible, filters, sort, onFilter, onSort } = useTable({
    rows: leases ?? [],
    accessors,
    numericAccessors,
  });

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
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Click a column header to sort; type below to filter that column.
          Dynamic leases can be reserved as static (the router converts the
          row in-place, keeping the same IP).
        </p>
        <span className="text-xs text-muted-foreground">
          {visible.length} of {leases?.length ?? 0}
        </span>
      </div>

      <div className="mt-3 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <TableHeader
            columns={cols}
            sort={sort}
            onSort={onSort}
            filters={filters}
            onFilter={onFilter}
          />
          <tbody className="divide-y divide-border">
            {(visible.length === 0 || isLoading) && (
              <EmptyRow
                span={cols.length}
                isLoading={isLoading}
                empty="No leases match."
              />
            )}
            {visible.map((l) => (
              <LeaseRow
                key={l.id ?? `${l.address}-${l.mac_address}`}
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
  const canReserve = lease.dynamic && lease.id !== null;
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
      </td>
      <td className="px-3 py-2 text-xs">{lease.server ?? "—"}</td>
      <td className="px-3 py-2 text-xs">
        {lease.dynamic ? (
          <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-amber-900">
            dynamic
          </span>
        ) : (
          <span className="rounded-md bg-sky-100 px-1.5 py-0.5 text-sky-900">
            static
          </span>
        )}
        {lease.blocked && (
          <span className="ml-1 rounded-md bg-red-100 px-1.5 py-0.5 text-red-900">
            blocked
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {lease.expires_at_iso ?? "—"}
      </td>
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
        {canReserve ? (
          <button
            type="button"
            onClick={onMakeStatic}
            className="mr-3 rounded-md border border-primary/40 bg-primary/5 px-2 py-0.5 font-medium text-primary hover:bg-primary/10"
            title="Convert this dynamic lease into a static reservation (same IP, MAC bound)"
          >
            Reserve
          </button>
        ) : (
          !lease.dynamic && (
            <span className="mr-3 text-[10px] uppercase tracking-wide text-muted-foreground">
              reserved
            </span>
          )
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

  const cols: ColDef[] = [
    { id: "name", label: "Name" },
    { id: "interface", label: "Interface" },
    { id: "address_pool", label: "Pool" },
    { id: "lease_time", label: "Lease time" },
    { id: "authoritative", label: "Authoritative" },
    { id: "status", label: "Status" },
    { id: "comment", label: "Comment" },
    { id: "actions", label: "", align: "right", noFilter: true, noSort: true },
  ];
  const accessors: Record<string, (r: DhcpServer) => string> = {
    name: (r) => r.name,
    interface: (r) => r.interface,
    address_pool: (r) => r.address_pool ?? "",
    lease_time: (r) => r.lease_time ?? "",
    authoritative: (r) => r.authoritative ?? "",
    status: (r) => (r.disabled ? "disabled" : "active"),
    comment: (r) => r.comment ?? "",
    actions: () => "",
  };
  const { visible, filters, sort, onFilter, onSort } = useTable({
    rows: servers ?? [],
    accessors,
  });

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
          <TableHeader
            columns={cols}
            sort={sort}
            onSort={onSort}
            filters={filters}
            onFilter={onFilter}
          />
          <tbody className="divide-y divide-border">
            {(visible.length === 0 || isLoading) && (
              <EmptyRow
                span={cols.length}
                isLoading={isLoading}
                empty="No servers match."
              />
            )}
            {visible.map((s) => (
              <tr key={s.id ?? s.name} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-medium">{s.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{s.interface}</td>
                <td className="px-3 py-2 text-xs">{s.address_pool ?? "—"}</td>
                <td className="px-3 py-2 text-xs">{s.lease_time ?? "—"}</td>
                <td className="px-3 py-2 text-xs">{s.authoritative ?? "—"}</td>
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
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {s.comment ?? "—"}
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
        <FormLabel label="Name">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="dhcp-lan"
          />
        </FormLabel>
        <FormLabel label="Interface">
          <input
            required
            value={iface}
            onChange={(e) => setIface(e.target.value)}
            className={`${input} font-mono`}
            placeholder="bridge-lan"
          />
        </FormLabel>
        <FormLabel label="Address pool">
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
        </FormLabel>
        <FormLabel label="Lease time">
          <input
            value={leaseTime}
            onChange={(e) => setLeaseTime(e.target.value)}
            className={input}
            placeholder="1d, 30m, 12h"
          />
        </FormLabel>
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

  const cols: ColDef[] = [
    { id: "address", label: "Address" },
    { id: "gateway", label: "Gateway" },
    { id: "dns_servers", label: "DNS" },
    { id: "ntp_servers", label: "NTP" },
    { id: "domain", label: "Domain" },
    { id: "comment", label: "Comment" },
    { id: "actions", label: "", align: "right", noFilter: true, noSort: true },
  ];
  const accessors: Record<string, (r: DhcpNetwork) => string> = {
    address: (r) => r.address,
    gateway: (r) => r.gateway ?? "",
    dns_servers: (r) => r.dns_servers ?? "",
    ntp_servers: (r) => r.ntp_servers ?? "",
    domain: (r) => r.domain ?? "",
    comment: (r) => r.comment ?? "",
    actions: () => "",
  };
  const numericAccessors: Record<string, (r: DhcpNetwork) => number> = {
    address: (r) => ipToInt(r.address),
    gateway: (r) => (r.gateway ? ipToInt(r.gateway) : 0),
  };
  const { visible, filters, sort, onFilter, onSort } = useTable({
    rows: networks ?? [],
    accessors,
    numericAccessors,
  });

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
          <TableHeader
            columns={cols}
            sort={sort}
            onSort={onSort}
            filters={filters}
            onFilter={onFilter}
          />
          <tbody className="divide-y divide-border">
            {(visible.length === 0 || isLoading) && (
              <EmptyRow
                span={cols.length}
                isLoading={isLoading}
                empty="No networks defined."
              />
            )}
            {visible.map((n) => (
              <tr key={n.id ?? n.address} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-mono text-xs">{n.address}</td>
                <td className="px-3 py-2 font-mono text-xs">{n.gateway ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{n.dns_servers ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{n.ntp_servers ?? "—"}</td>
                <td className="px-3 py-2 text-xs">{n.domain ?? "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {n.comment ?? "—"}
                </td>
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
        <FormLabel label="Network (CIDR)">
          <input
            required
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.0/24"
          />
        </FormLabel>
        <FormLabel label="Gateway">
          <input
            value={gateway}
            onChange={(e) => setGateway(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.1"
          />
        </FormLabel>
        <FormLabel label="DNS servers">
          <input
            value={dns}
            onChange={(e) => setDns(e.target.value)}
            className={`${input} font-mono`}
          />
        </FormLabel>
        <FormLabel label="NTP servers">
          <input
            value={ntp}
            onChange={(e) => setNtp(e.target.value)}
            className={`${input} font-mono`}
            placeholder="pool.ntp.org"
          />
        </FormLabel>
        <FormLabel label="Domain">
          <input
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            className={input}
            placeholder="corp.local"
          />
        </FormLabel>
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

  const cols: ColDef[] = [
    { id: "name", label: "Name" },
    { id: "ranges", label: "Ranges" },
    { id: "next_pool", label: "Next pool" },
    { id: "comment", label: "Comment" },
    { id: "actions", label: "", align: "right", noFilter: true, noSort: true },
  ];
  const accessors: Record<string, (r: DhcpPool) => string> = {
    name: (r) => r.name,
    ranges: (r) => r.ranges,
    next_pool: (r) => r.next_pool ?? "",
    comment: (r) => r.comment ?? "",
    actions: () => "",
  };
  const { visible, filters, sort, onFilter, onSort } = useTable({
    rows: pools ?? [],
    accessors,
  });

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
          <TableHeader
            columns={cols}
            sort={sort}
            onSort={onSort}
            filters={filters}
            onFilter={onFilter}
          />
          <tbody className="divide-y divide-border">
            {(visible.length === 0 || isLoading) && (
              <EmptyRow
                span={cols.length}
                isLoading={isLoading}
                empty="No pools defined."
              />
            )}
            {visible.map((p) => (
              <PoolRow
                key={p.id ?? p.name}
                pool={p}
                deviceId={deviceId}
                onDelete={() => {
                  if (p.id && confirm(`Delete pool "${p.name}"?`)) del.mutate(p.id);
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PoolRow({
  pool,
  deviceId,
  onDelete,
}: {
  pool: DhcpPool;
  deviceId: string;
  onDelete: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(pool.name);
  const [ranges, setRanges] = useState(pool.ranges);
  const [nextPool, setNextPool] = useState(pool.next_pool ?? "");
  const [comment, setComment] = useState(pool.comment ?? "");
  const [error, setError] = useState<string | null>(null);

  function startEditing() {
    setName(pool.name);
    setRanges(pool.ranges);
    setNextPool(pool.next_pool ?? "");
    setComment(pool.comment ?? "");
    setError(null);
    setEditing(true);
  }

  const save = useMutation({
    mutationFn: () => {
      if (!pool.id) return Promise.reject(new Error("missing pool id"));
      return updateDhcpPool(deviceId, pool.id, {
        name,
        ranges,
        next_pool: nextPool || null,
        comment: comment || null,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dhcp-pools", deviceId] });
      toast.success("Pool updated");
      setEditing(false);
    },
    onError: (e: Error) => setError(e.message),
  });

  if (!editing) {
    return (
      <tr className="hover:bg-accent/30">
        <td className="px-3 py-2 font-medium">{pool.name}</td>
        <td className="px-3 py-2 font-mono text-xs">{pool.ranges}</td>
        <td className="px-3 py-2 font-mono text-xs">{pool.next_pool ?? "—"}</td>
        <td className="px-3 py-2 text-xs text-muted-foreground">
          {pool.comment ?? "—"}
        </td>
        <td className="px-3 py-2 text-right text-xs">
          {pool.id && (
            <button
              type="button"
              onClick={startEditing}
              className="mr-3 text-primary hover:underline"
            >
              Edit
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

  return (
    <tr className="bg-accent/20 align-top">
      <td className="px-3 py-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={`${input} text-sm`}
        />
      </td>
      <td className="px-3 py-2">
        <input
          value={ranges}
          onChange={(e) => setRanges(e.target.value)}
          className={`${input} font-mono text-xs`}
          placeholder="10.0.0.10-10.0.0.250"
        />
      </td>
      <td className="px-3 py-2">
        <input
          value={nextPool}
          onChange={(e) => setNextPool(e.target.value)}
          className={`${input} font-mono text-xs`}
          placeholder="optional"
        />
      </td>
      <td className="px-3 py-2">
        <input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          className={`${input} text-xs`}
        />
        {error && (
          <p className="mt-1 text-[11px] text-destructive">{error}</p>
        )}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-right text-xs">
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="mr-2 rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => {
            setError(null);
            setEditing(false);
          }}
          className="text-muted-foreground hover:underline"
        >
          Cancel
        </button>
      </td>
    </tr>
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
        <FormLabel label="Name">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="lan-pool"
          />
        </FormLabel>
        <FormLabel label="Ranges">
          <input
            required
            value={ranges}
            onChange={(e) => setRanges(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.10-10.0.0.250"
          />
        </FormLabel>
        <FormLabel label="Comment">
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={input}
          />
        </FormLabel>
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

function FormLabel({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1 text-sm font-medium">
      {label}
      {children}
    </label>
  );
}

// IPv4 → 32-bit integer for numeric sort. Returns 0 for anything that
// isn't a dotted-quad so non-IPs sort to the top under "asc".
function ipToInt(s: string): number {
  const head = s.split("/")[0]?.split("-")[0]?.trim();
  if (!head) return 0;
  const parts = head.split(".");
  if (parts.length !== 4) return 0;
  let acc = 0;
  for (const p of parts) {
    const n = Number(p);
    if (!Number.isFinite(n) || n < 0 || n > 255) return 0;
    acc = acc * 256 + n;
  }
  return acc;
}

// Silence unused-import warnings until the edit forms come online.
void updateDhcpNetwork;
void updateDhcpServer;

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
