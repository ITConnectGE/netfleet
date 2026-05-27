"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import {
  createRoute,
  createVlan,
  deleteRoute,
  deleteVlan,
  formatBytes,
  listArp,
  listBridgeHosts,
  listInterfaces,
  listNeighbors,
  listRoutes,
  listVlans,
  type ArpEntry,
  type BridgeHost,
  type Interface,
  type IpRoute,
  type Neighbor,
  type Vlan,
} from "@/lib/network";

type Tab = "interfaces" | "routes" | "vlans" | "arp" | "bridge" | "neighbors";

export default function NetworkPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const [tab, setTab] = useState<Tab>("interfaces");

  return (
    <div>
      <div className="mb-4 inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
        {(
          [
            ["interfaces", "Interfaces"],
            ["routes", "Routes"],
            ["vlans", "VLANs"],
            ["arp", "ARP"],
            ["bridge", "Bridge hosts"],
            ["neighbors", "Neighbors (CDP/LLDP)"],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`rounded px-3 py-1.5 font-medium transition ${
              tab === k
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "interfaces" && <InterfacesTab deviceId={deviceId} />}
      {tab === "routes" && <RoutesTab deviceId={deviceId} />}
      {tab === "vlans" && <VlansTab deviceId={deviceId} />}
      {tab === "arp" && <ArpTab deviceId={deviceId} />}
      {tab === "bridge" && <BridgeTab deviceId={deviceId} />}
      {tab === "neighbors" && <NeighborsTab deviceId={deviceId} />}
    </div>
  );
}

// ---------------- Neighbours ----------------

function NeighborsTab({ deviceId }: { deviceId: string }) {
  const { data, isLoading, error } = useQuery<Neighbor[]>({
    queryKey: ["neighbors", deviceId],
    queryFn: () => listNeighbors(deviceId),
  });
  return (
    <Section
      title="Neighbors (CDP / LLDP / MNDP)"
      subtitle="Other devices the router has seen advertise themselves on its links. Useful for mapping the physical/L2 topology."
    >
      <ErrorOrTable error={error}>
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">Local port</th>
              <th className="px-3 py-2 font-medium">Identity</th>
              <th className="px-3 py-2 font-medium">Address</th>
              <th className="px-3 py-2 font-medium">MAC</th>
              <th className="px-3 py-2 font-medium">Platform</th>
              <th className="px-3 py-2 font-medium">Version</th>
              <th className="px-3 py-2 font-medium">Board</th>
              <th className="px-3 py-2 font-medium">Remote port</th>
              <th className="px-3 py-2 font-medium">Proto</th>
              <th className="px-3 py-2 font-medium">Age</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && <EmptyRow colSpan={10} label="Loading…" />}
            {!isLoading && (!data || data.length === 0) && (
              <EmptyRow
                colSpan={10}
                label="No neighbours discovered. Enable LLDP/CDP under /ip neighbor discovery-settings on the device."
              />
            )}
            {data?.map((n) => (
              <tr key={n.id ?? `${n.mac_address}-${n.interface}`} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-mono text-xs">{n.interface ?? "—"}</td>
                <td className="px-3 py-2 font-medium">{n.identity ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">
                  {n.address ?? n.address6 ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-[11px]">{n.mac_address ?? "—"}</td>
                <td className="px-3 py-2 text-xs">{n.platform ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{n.version ?? "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{n.board ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{n.interface_name ?? "—"}</td>
                <td className="px-3 py-2 text-xs">
                  {n.discovered_by ? (
                    <span className="rounded-md bg-sky-100 px-1.5 py-0.5 text-[10px] text-sky-900">
                      {n.discovered_by}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{n.age ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ErrorOrTable>
    </Section>
  );
}

// ---------------- Interfaces ----------------

function InterfacesTab({ deviceId }: { deviceId: string }) {
  const { data, isLoading, error } = useQuery<Interface[]>({
    queryKey: ["interfaces", deviceId],
    queryFn: () => listInterfaces(deviceId),
  });

  return (
    <Section title="Interfaces" subtitle="All interfaces with link state and counters.">
      <ErrorOrTable error={error}>
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">MAC</th>
              <th className="px-3 py-2 font-medium">MTU</th>
              <th className="px-3 py-2 font-medium text-right">RX</th>
              <th className="px-3 py-2 font-medium text-right">TX</th>
              <th className="px-3 py-2 font-medium">State</th>
              <th className="px-3 py-2 font-medium">Comment</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && <EmptyRow colSpan={8} label="Loading…" />}
            {!isLoading && (!data || data.length === 0) && (
              <EmptyRow colSpan={8} label="No interfaces." />
            )}
            {data?.map((i) => (
              <tr key={i.id ?? i.name} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-medium">{i.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{i.type}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{i.mac_address ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{i.mtu ?? "—"}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatBytes(i.rx_bytes)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatBytes(i.tx_bytes)}
                </td>
                <td className="px-3 py-2 text-xs">
                  {i.disabled ? (
                    <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-800">
                      disabled
                    </span>
                  ) : i.running ? (
                    <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800">
                      running
                    </span>
                  ) : (
                    <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-900">
                      down
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{i.comment ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ErrorOrTable>
    </Section>
  );
}

// ---------------- Routes ----------------

function RoutesTab({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const { data, isLoading, error } = useQuery<IpRoute[]>({
    queryKey: ["routes", deviceId],
    queryFn: () => listRoutes(deviceId),
  });
  const del = useMutation({
    mutationFn: (id: string) => deleteRoute(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["routes", deviceId] }),
  });

  return (
    <Section
      title="IP routes"
      subtitle="Static + dynamic routing table."
      action={
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New route"}
        </button>
      }
    >
      {showForm && (
        <RouteForm
          deviceId={deviceId}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["routes", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <ErrorOrTable error={error}>
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">Destination</th>
              <th className="px-3 py-2 font-medium">Gateway</th>
              <th className="px-3 py-2 font-medium">Distance</th>
              <th className="px-3 py-2 font-medium">Table</th>
              <th className="px-3 py-2 font-medium">Flags</th>
              <th className="px-3 py-2 font-medium">Comment</th>
              <th className="px-3 py-2 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && <EmptyRow colSpan={7} label="Loading…" />}
            {!isLoading && (!data || data.length === 0) && (
              <EmptyRow colSpan={7} label="No routes." />
            )}
            {data?.map((r) => (
              <tr key={r.id} className={`hover:bg-accent/30 ${r.disabled ? "opacity-50" : ""}`}>
                <td className="px-3 py-2 font-mono text-xs">{r.dst_address}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.gateway ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.distance ?? "—"}</td>
                <td className="px-3 py-2 text-xs">{r.routing_table ?? "main"}</td>
                <td className="px-3 py-2 text-xs">
                  {r.active && (
                    <span className="mr-1 rounded bg-emerald-100 px-1 py-0.5 text-[10px] text-emerald-800">
                      A
                    </span>
                  )}
                  {r.dynamic && (
                    <span className="mr-1 rounded bg-sky-100 px-1 py-0.5 text-[10px] text-sky-900">
                      D
                    </span>
                  )}
                  {r.static && (
                    <span className="mr-1 rounded bg-violet-100 px-1 py-0.5 text-[10px] text-violet-900">
                      S
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{r.comment ?? "—"}</td>
                <td className="px-3 py-2 text-right">
                  {!r.dynamic && r.id && (
                    <button
                      onClick={() => {
                        if (confirm(`Delete route to ${r.dst_address}?`)) del.mutate(r.id!);
                      }}
                      className="text-xs text-destructive hover:underline"
                    >
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ErrorOrTable>
    </Section>
  );
}

function RouteForm({
  deviceId,
  onCreated,
}: {
  deviceId: string;
  onCreated: () => void;
}) {
  const [dst, setDst] = useState("0.0.0.0/0");
  const [gw, setGw] = useState("");
  const [distance, setDistance] = useState<number | "">(1);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createRoute(deviceId, {
        dst_address: dst,
        gateway: gw || null,
        distance: typeof distance === "number" ? distance : null,
        comment: comment || null,
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
      className="mb-4 rounded-lg border border-border bg-card p-4"
    >
      {error && (
        <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-4">
        <Field label="Destination" htmlFor="r-dst">
          <input
            id="r-dst"
            required
            value={dst}
            onChange={(e) => setDst(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.20.0.0/24"
          />
        </Field>
        <Field label="Gateway" htmlFor="r-gw">
          <input
            id="r-gw"
            value={gw}
            onChange={(e) => setGw(e.target.value)}
            className={`${input} font-mono`}
            placeholder="192.168.1.1"
          />
        </Field>
        <Field label="Distance" htmlFor="r-d">
          <input
            id="r-d"
            type="number"
            min={1}
            max={255}
            value={distance}
            onChange={(e) => setDistance(e.target.value === "" ? "" : Number(e.target.value))}
            className={input}
          />
        </Field>
        <Field label="Comment" htmlFor="r-c">
          <input
            id="r-c"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={input}
          />
        </Field>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Adding…" : "Add route"}
        </button>
      </div>
    </form>
  );
}

// ---------------- VLANs ----------------

function VlansTab({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const { data, isLoading, error } = useQuery<Vlan[]>({
    queryKey: ["vlans", deviceId],
    queryFn: () => listVlans(deviceId),
  });
  const { data: interfaces } = useQuery<Interface[]>({
    queryKey: ["interfaces", deviceId],
    queryFn: () => listInterfaces(deviceId),
  });
  const del = useMutation({
    mutationFn: (id: string) => deleteVlan(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vlans", deviceId] }),
  });

  return (
    <Section
      title="VLANs"
      subtitle="Virtual LANs on top of an existing interface (typically a bridge or ether)."
      action={
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New VLAN"}
        </button>
      }
    >
      {showForm && interfaces && (
        <VlanForm
          deviceId={deviceId}
          interfaces={interfaces}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["vlans", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <ErrorOrTable error={error}>
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">VLAN ID</th>
              <th className="px-3 py-2 font-medium">Parent interface</th>
              <th className="px-3 py-2 font-medium">MTU</th>
              <th className="px-3 py-2 font-medium">Comment</th>
              <th className="px-3 py-2 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && <EmptyRow colSpan={6} label="Loading…" />}
            {!isLoading && (!data || data.length === 0) && (
              <EmptyRow colSpan={6} label="No VLANs defined." />
            )}
            {data?.map((v) => (
              <tr key={v.id ?? v.name} className={`hover:bg-accent/30 ${v.disabled ? "opacity-50" : ""}`}>
                <td className="px-3 py-2 font-medium">{v.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{v.vlan_id}</td>
                <td className="px-3 py-2 font-mono text-xs">{v.interface}</td>
                <td className="px-3 py-2 font-mono text-xs">{v.mtu ?? "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{v.comment ?? "—"}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => {
                      if (v.id && confirm(`Delete VLAN ${v.name}?`)) del.mutate(v.id);
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
      </ErrorOrTable>
    </Section>
  );
}

function VlanForm({
  deviceId,
  interfaces,
  onCreated,
}: {
  deviceId: string;
  interfaces: Interface[];
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [iface, setIface] = useState(interfaces[0]?.name ?? "");
  const [vlanId, setVlanId] = useState(10);
  const [mtu, setMtu] = useState<number | "">(1500);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createVlan(deviceId, {
        name,
        interface: iface,
        vlan_id: vlanId,
        mtu: typeof mtu === "number" ? mtu : null,
        comment: comment || null,
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
      className="mb-4 rounded-lg border border-border bg-card p-4"
    >
      {error && (
        <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-4">
        <Field label="Name" htmlFor="v-n">
          <input
            id="v-n"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="vlan10-guest"
          />
        </Field>
        <Field label="VLAN ID" htmlFor="v-id">
          <input
            id="v-id"
            type="number"
            min={1}
            max={4094}
            required
            value={vlanId}
            onChange={(e) => setVlanId(Number(e.target.value))}
            className={input}
          />
        </Field>
        <Field label="Parent interface" htmlFor="v-if">
          <select
            id="v-if"
            value={iface}
            onChange={(e) => setIface(e.target.value)}
            className={input}
          >
            {interfaces.map((i) => (
              <option key={i.name} value={i.name}>
                {i.name} ({i.type})
              </option>
            ))}
          </select>
        </Field>
        <Field label="MTU" htmlFor="v-mtu">
          <input
            id="v-mtu"
            type="number"
            min={576}
            max={9000}
            value={mtu}
            onChange={(e) => setMtu(e.target.value === "" ? "" : Number(e.target.value))}
            className={input}
          />
        </Field>
        <Field label="Comment" htmlFor="v-c">
          <input
            id="v-c"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={input}
          />
        </Field>
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Adding…" : "Add VLAN"}
        </button>
      </div>
    </form>
  );
}

// ---------------- ARP ----------------

function ArpTab({ deviceId }: { deviceId: string }) {
  const { data, isLoading, error } = useQuery<ArpEntry[]>({
    queryKey: ["arp", deviceId],
    queryFn: () => listArp(deviceId),
  });
  return (
    <Section title="ARP table" subtitle="IP ↔ MAC mapping the router currently has resolved.">
      <ErrorOrTable error={error}>
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">IP</th>
              <th className="px-3 py-2 font-medium">MAC</th>
              <th className="px-3 py-2 font-medium">Interface</th>
              <th className="px-3 py-2 font-medium">Flags</th>
              <th className="px-3 py-2 font-medium">Comment</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && <EmptyRow colSpan={5} label="Loading…" />}
            {!isLoading && (!data || data.length === 0) && (
              <EmptyRow colSpan={5} label="ARP table is empty." />
            )}
            {data?.map((a) => (
              <tr key={a.id ?? `${a.address}-${a.mac_address}`} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-mono text-xs">{a.address}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{a.mac_address ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{a.interface ?? "—"}</td>
                <td className="px-3 py-2 text-xs">
                  {a.dynamic && (
                    <span className="mr-1 rounded bg-sky-100 px-1 py-0.5 text-[10px] text-sky-900">
                      dyn
                    </span>
                  )}
                  {a.complete && (
                    <span className="mr-1 rounded bg-emerald-100 px-1 py-0.5 text-[10px] text-emerald-800">
                      ok
                    </span>
                  )}
                  {a.invalid && (
                    <span className="mr-1 rounded bg-red-100 px-1 py-0.5 text-[10px] text-red-800">
                      inv
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{a.comment ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ErrorOrTable>
    </Section>
  );
}

// ---------------- Bridge hosts ----------------

function BridgeTab({ deviceId }: { deviceId: string }) {
  const { data, isLoading, error } = useQuery<BridgeHost[]>({
    queryKey: ["bridge-hosts", deviceId],
    queryFn: () => listBridgeHosts(deviceId),
  });
  return (
    <Section title="Bridge hosts" subtitle="MAC addresses the bridge has learned on each port.">
      <ErrorOrTable error={error}>
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">MAC</th>
              <th className="px-3 py-2 font-medium">Port</th>
              <th className="px-3 py-2 font-medium">Bridge</th>
              <th className="px-3 py-2 font-medium">Age</th>
              <th className="px-3 py-2 font-medium">Flags</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && <EmptyRow colSpan={5} label="Loading…" />}
            {!isLoading && (!data || data.length === 0) && (
              <EmptyRow colSpan={5} label="Bridge has not learned any hosts yet." />
            )}
            {data?.map((h) => (
              <tr key={h.id ?? `${h.mac_address}-${h.on_interface}`} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-mono text-[11px]">{h.mac_address}</td>
                <td className="px-3 py-2 font-mono text-xs">{h.on_interface ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{h.bridge ?? "—"}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{h.age ?? "—"}</td>
                <td className="px-3 py-2 text-xs">
                  {h.dynamic && (
                    <span className="mr-1 rounded bg-sky-100 px-1 py-0.5 text-[10px] text-sky-900">
                      dyn
                    </span>
                  )}
                  {h.external && (
                    <span className="mr-1 rounded bg-amber-100 px-1 py-0.5 text-[10px] text-amber-900">
                      ext
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ErrorOrTable>
    </Section>
  );
}

// ---------------- Shared bits ----------------

function Section({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function ErrorOrTable({
  error,
  children,
}: {
  error: unknown;
  children: React.ReactNode;
}) {
  return (
    <>
      {error && (
        <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border border-border bg-card">{children}</div>
    </>
  );
}

function EmptyRow({ colSpan, label }: { colSpan: number; label: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-6 text-center text-muted-foreground">
        {label}
      </td>
    </tr>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
