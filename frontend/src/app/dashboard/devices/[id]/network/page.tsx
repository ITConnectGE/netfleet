"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";

import { useToast } from "@/components/toast";
import {
  createRoute,
  createVlan,
  deleteRoute,
  deleteVlan,
  formatBytes,
  getNeighborDiscovery,
  listArp,
  listBridgeHosts,
  listInterfaceListMembers,
  listInterfaceLists,
  listInterfaces,
  listNeighbors,
  listRoutes,
  listVlans,
  resetInterfaceCounters,
  setNeighborDiscovery,
  type ArpEntry,
  type BridgeHost,
  type Interface,
  type InterfaceList,
  type InterfaceListMember,
  type IpRoute,
  type Neighbor,
  type NeighborDiscovery,
  type Vlan,
} from "@/lib/network";
import { getDevice, type Device } from "@/lib/devices";

type Tab =
  | "interfaces"
  | "interface-lists"
  | "routes"
  | "vlans"
  | "arp"
  | "bridge"
  | "neighbors";

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
            ["interface-lists", "Interface lists"],
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
      {tab === "interface-lists" && <InterfaceListsTab deviceId={deviceId} />}
      {tab === "routes" && <RoutesTab deviceId={deviceId} />}
      {tab === "vlans" && <VlansTab deviceId={deviceId} />}
      {tab === "arp" && <ArpTab deviceId={deviceId} />}
      {tab === "bridge" && <BridgeTab deviceId={deviceId} />}
      {tab === "neighbors" && <NeighborsTab deviceId={deviceId} />}
    </div>
  );
}

// ---------------- Neighbours ----------------

const ALL_PROTOCOLS = ["cdp", "lldp", "mndp"] as const;
type ProtocolKey = (typeof ALL_PROTOCOLS)[number];

function parseProtocols(s: string | null): Set<ProtocolKey> {
  if (!s) return new Set();
  return new Set(
    s
      .split(",")
      .map((p) => p.trim().toLowerCase())
      .filter((p): p is ProtocolKey =>
        (ALL_PROTOCOLS as readonly string[]).includes(p),
      ),
  );
}

function NeighborsTab({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const [view, setView] = useState<"table" | "graph">("graph");
  const { data, isLoading, error } = useQuery<Neighbor[]>({
    queryKey: ["neighbors", deviceId],
    queryFn: () => listNeighbors(deviceId),
    refetchInterval: 30_000,
  });
  const { data: device } = useQuery<Device>({
    queryKey: ["device", deviceId],
    queryFn: () => getDevice(deviceId),
  });
  const { data: discovery } = useQuery<NeighborDiscovery>({
    queryKey: ["neighbor-discovery", deviceId],
    queryFn: () => getNeighborDiscovery(deviceId),
  });

  const enabledProtocols = parseProtocols(discovery?.protocols ?? null);
  const ifaceList = discovery?.discover_interface_list ?? null;
  // RouterOS treats "none" or an empty interface list as "discovery off
  // everywhere". Anything else — "all", "!dynamic", "WAN", … — is "on".
  const interfacesOn = Boolean(
    ifaceList && ifaceList !== "" && ifaceList !== "none",
  );
  const allProtocolsOn =
    ALL_PROTOCOLS.every((p) => enabledProtocols.has(p)) && interfacesOn;
  const discoveryOff = !interfacesOn || enabledProtocols.size === 0;

  const setDiscovery = useMutation({
    mutationFn: (payload: NeighborDiscovery) => setNeighborDiscovery(deviceId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["neighbor-discovery", deviceId] });
      qc.invalidateQueries({ queryKey: ["neighbors", deviceId] });
    },
  });

  const toggleProtocol = (p: ProtocolKey) => {
    const next = new Set(enabledProtocols);
    if (next.has(p)) next.delete(p);
    else next.add(p);
    setDiscovery.mutate({
      discover_interface_list: interfacesOn ? ifaceList : "all",
      protocols: ALL_PROTOCOLS.filter((x) => next.has(x)).join(",") || "",
    });
  };
  const enableAll = () =>
    setDiscovery.mutate({
      discover_interface_list: "all",
      protocols: "cdp,lldp,mndp",
    });

  return (
    <Section
      title="Neighbors (CDP / LLDP / MNDP)"
      subtitle="Other devices the router has seen advertise themselves on its links. Useful for mapping the physical/L2 topology."
      action={
        <div className="inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
          {(["graph", "table"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setView(k)}
              className={`rounded px-2.5 py-1 font-medium transition ${
                view === k
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {k === "graph" ? "Graph" : "Table"}
            </button>
          ))}
        </div>
      }
    >
      {error && (
        <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      {/* Discovery status + per-protocol toggles. The pills reflect the
          actual `/ip/neighbor/discovery-settings` state and clicking one
          patches the device immediately. */}
      <div className="mb-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">Discovery:</span>
            {discovery ? (
              <>
                {ALL_PROTOCOLS.map((p) => {
                  const on = enabledProtocols.has(p);
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => toggleProtocol(p)}
                      disabled={setDiscovery.isPending}
                      title={on ? `Click to disable ${p.toUpperCase()}` : `Click to enable ${p.toUpperCase()}`}
                      className={`rounded-md px-2 py-0.5 text-[11px] font-medium uppercase transition disabled:opacity-50 ${
                        on
                          ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-200"
                          : "bg-zinc-200 text-zinc-600 line-through hover:bg-zinc-300"
                      }`}
                    >
                      {p}
                    </button>
                  );
                })}
                <span className="text-muted-foreground">·</span>
                <span className="font-mono text-muted-foreground">
                  interfaces={ifaceList ?? "—"}
                </span>
              </>
            ) : (
              <span className="text-muted-foreground">…</span>
            )}
          </div>
          {discoveryOff && (
            <button
              onClick={enableAll}
              disabled={setDiscovery.isPending}
              className="rounded-md bg-emerald-600 px-3 py-1 text-xs font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {setDiscovery.isPending
                ? "Enabling…"
                : "Enable on all interfaces (CDP+LLDP+MNDP)"}
            </button>
          )}
        </div>
        {!discoveryOff && !allProtocolsOn && (
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            Some protocols are disabled. Click a greyed pill to toggle it on.
          </p>
        )}
      </div>
      {setDiscovery.error && (
        <div className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(setDiscovery.error as Error).message}
        </div>
      )}

      {view === "graph" ? (
        <NeighborsGraph
          centerName={device?.name ?? "this device"}
          centerPlatform="MikroTik"
          neighbors={data ?? []}
          isLoading={isLoading}
          emptyHeadline={
            discoveryOff
              ? "Discovery is off on this device."
              : !allProtocolsOn
                ? `Discovery is partially on (${[...enabledProtocols].join(", ").toUpperCase() || "none"}).`
                : "No neighbours yet."
          }
          emptyBody={
            discoveryOff
              ? "Turn it on with the button above and give the device a few seconds to advertise."
              : !allProtocolsOn
                ? "Some peers may not be reached. Toggle the missing protocols above to widen the net."
                : "Discovery is on. Check that peer devices advertise via CDP, LLDP or MNDP and are connected to one of this router's interfaces."
          }
          emptyState={
            discoveryOff ? (
              <button
                onClick={enableAll}
                disabled={setDiscovery.isPending}
                className="mt-3 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
              >
                {setDiscovery.isPending ? "Enabling…" : "Enable discovery now"}
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
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
                  label="No neighbours discovered. Use the Enable button above."
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
        </div>
      )}
    </Section>
  );
}

// Radial SVG of the device and its discovered neighbours. No new deps;
// pure SVG + simple polar layout. With >40 peers it gets crowded — at
// that scale the table is still the right view, hence the toggle.
function NeighborsGraph({
  centerName,
  centerPlatform,
  neighbors,
  isLoading,
  emptyHeadline,
  emptyBody,
  emptyState,
}: {
  centerName: string;
  centerPlatform: string;
  neighbors: Neighbor[];
  isLoading: boolean;
  emptyHeadline?: string;
  emptyBody?: string;
  emptyState?: React.ReactNode;
}) {
  const [hovered, setHovered] = useState<number | null>(null);

  if (isLoading) {
    return (
      <div className="flex h-80 items-center justify-center rounded-lg border border-border bg-card text-sm text-muted-foreground">
        Loading topology…
      </div>
    );
  }
  if (neighbors.length === 0) {
    return (
      <div className="flex h-80 flex-col items-center justify-center rounded-lg border border-border bg-card p-6 text-center text-sm text-muted-foreground">
        <p className="font-medium text-foreground">
          {emptyHeadline ?? "No neighbours discovered."}
        </p>
        {emptyBody && <p className="mt-1 text-xs">{emptyBody}</p>}
        {emptyState}
      </div>
    );
  }

  // Canvas + layout — the device sits pinned to the top-centre, peers fan
  // out in a semicircle below it. This matches how an MSP usually thinks
  // about the topology: the router we manage IS the edge, neighbours hang
  // off it. We deliberately don't put the device in the middle of the
  // canvas because that visually implies "centre of the network" which it
  // almost never is.
  const w = 800;
  const h = Math.max(440, 240 + neighbors.length * 16);
  const cx = w / 2;
  const cy = 80;
  // Fan peers across the lower half. ANGLE_* are measured in SVG
  // convention (y axis points down, so positive angle = downward arc).
  const ANGLE_START = Math.PI * 0.15;
  const ANGLE_END = Math.PI * 0.85;
  // Clamp radius so the widest peer node still fits within the canvas
  // even when the fan is most splayed (angle = ANGLE_START).
  const NODE_HALF = 70;
  const verticalRoom = h - cy - 100;
  const horizontalRoom = (w / 2 - NODE_HALF) / Math.cos(ANGLE_START);
  const radius = Math.min(verticalRoom, horizontalRoom);
  const nodes = neighbors.map((n, i) => {
    const angle =
      neighbors.length === 1
        ? Math.PI / 2
        : ANGLE_START + (i / (neighbors.length - 1)) * (ANGLE_END - ANGLE_START);
    return {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
      angle,
      neighbor: n,
    };
  });

  return (
    <div className="rounded-lg border border-border bg-card p-2">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="block h-auto w-full"
        role="img"
        aria-label="Network topology — local device at top, neighbours fanning out below"
      >
        {/* Edges first so nodes paint on top. */}
        {nodes.map((node, i) => {
          const hl = hovered === i;
          return (
            <g key={`edge-${i}`}>
              <line
                x1={cx}
                y1={cy}
                x2={node.x}
                y2={node.y}
                stroke={hl ? "#0ea5e9" : "#cbd5e1"}
                strokeWidth={hl ? 2 : 1.3}
              />
              {node.neighbor.interface && (
                <EdgeLabel
                  x1={cx}
                  y1={cy}
                  x2={node.x}
                  y2={node.y}
                  text={node.neighbor.interface}
                  highlighted={hl}
                />
              )}
            </g>
          );
        })}

        {/* Centre node */}
        <NodeShape
          x={cx}
          y={cy}
          label={centerName}
          sublabel={centerPlatform}
          color={platformColor(centerPlatform)}
          isCenter
        />

        {/* Peers */}
        {nodes.map((node, i) => {
          const n = node.neighbor;
          const labelMain = n.identity ?? n.address ?? n.mac_address ?? "?";
          const sub = n.platform ?? n.board ?? n.discovered_by ?? "";
          return (
            <g
              key={`peer-${i}`}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: "pointer" }}
            >
              <NodeShape
                x={node.x}
                y={node.y}
                label={labelMain}
                sublabel={sub}
                color={platformColor(n.platform)}
                isCenter={false}
              />
              {hovered === i && (
                <NodeTooltip x={node.x} y={node.y} neighbor={n} canvasW={w} />
              )}
            </g>
          );
        })}
      </svg>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-2 text-[11px] text-muted-foreground">
        <span>
          Showing {neighbors.length} neighbour{neighbors.length === 1 ? "" : "s"}.
          Lines label the local port; hover a node for full details.
        </span>
        <span className="inline-flex items-center gap-2">
          <PlatformDot platform="MikroTik" />
          MikroTik
          <PlatformDot platform="Cisco" />
          Cisco
          <PlatformDot platform="Ubiquiti" />
          Ubiquiti
          <PlatformDot platform={null} />
          other
        </span>
      </div>
    </div>
  );
}

function NodeShape({
  x,
  y,
  label,
  sublabel,
  color,
  isCenter,
}: {
  x: number;
  y: number;
  label: string;
  sublabel: string;
  color: string;
  isCenter: boolean;
}) {
  const w = isCenter ? 150 : 130;
  const h = isCenter ? 48 : 40;
  return (
    <g transform={`translate(${x - w / 2}, ${y - h / 2})`}>
      <rect
        width={w}
        height={h}
        rx={8}
        ry={8}
        fill="white"
        stroke={color}
        strokeWidth={isCenter ? 2.5 : 1.5}
      />
      <rect width={6} height={h} rx={3} ry={3} fill={color} />
      <text
        x={w / 2}
        y={isCenter ? 20 : 17}
        textAnchor="middle"
        className="fill-zinc-900"
        fontSize={isCenter ? 13 : 11}
        fontWeight={600}
      >
        {truncate(label, isCenter ? 18 : 16)}
      </text>
      <text
        x={w / 2}
        y={isCenter ? 36 : 30}
        textAnchor="middle"
        className="fill-zinc-500"
        fontSize={10}
      >
        {truncate(sublabel, 22)}
      </text>
    </g>
  );
}

function EdgeLabel({
  x1,
  y1,
  x2,
  y2,
  text,
  highlighted,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  text: string;
  highlighted: boolean;
}) {
  // Place the label ~40% along the line from centre so it sits clear of
  // both the centre node and the peer node.
  const t = 0.4;
  const mx = x1 + (x2 - x1) * t;
  const my = y1 + (y2 - y1) * t;
  const padX = 6;
  const labelWidth = text.length * 5.6 + padX * 2;
  return (
    <g transform={`translate(${mx - labelWidth / 2}, ${my - 8})`}>
      <rect
        width={labelWidth}
        height={14}
        rx={3}
        ry={3}
        fill={highlighted ? "#e0f2fe" : "#f1f5f9"}
        stroke={highlighted ? "#0ea5e9" : "#cbd5e1"}
      />
      <text
        x={labelWidth / 2}
        y={10}
        textAnchor="middle"
        fontFamily="monospace"
        fontSize={9}
        className="fill-zinc-700"
      >
        {text}
      </text>
    </g>
  );
}

function NodeTooltip({
  x,
  y,
  neighbor: n,
  canvasW,
}: {
  x: number;
  y: number;
  neighbor: Neighbor;
  canvasW: number;
}) {
  const lines: [string, string | null][] = [
    ["Identity", n.identity],
    ["Address", n.address ?? n.address6],
    ["MAC", n.mac_address],
    ["Platform", n.platform],
    ["Version", n.version],
    ["Board", n.board],
    ["Local port", n.interface],
    ["Remote port", n.interface_name],
    ["Proto", n.discovered_by],
    ["Age", n.age],
  ];
  const visible = lines.filter(([, v]) => v && v.length > 0);
  const lineHeight = 14;
  const padX = 8;
  const padY = 8;
  const boxW = 230;
  const boxH = padY * 2 + visible.length * lineHeight;
  // Flip the tooltip to the left side of the node when it would overflow
  // the right edge of the canvas.
  const onLeft = x + 30 + boxW > canvasW;
  const tx = onLeft ? x - 30 - boxW : x + 30;
  // Place above the node when it sits in the lower half of the canvas so
  // the tooltip never falls off the bottom edge.
  const ty = Math.max(8, y - boxH / 2);
  return (
    <g transform={`translate(${tx}, ${ty})`} pointerEvents="none">
      <rect
        width={boxW}
        height={boxH}
        rx={6}
        ry={6}
        fill="#0f172a"
        opacity={0.95}
      />
      {visible.map(([k, v], i) => (
        <g key={k} transform={`translate(${padX}, ${padY + i * lineHeight + 10})`}>
          <text fontSize={10} className="fill-zinc-400" fontWeight={500}>
            {k}
          </text>
          <text
            x={70}
            fontSize={10}
            fontFamily="monospace"
            className="fill-white"
          >
            {truncate(v ?? "", 24)}
          </text>
        </g>
      ))}
    </g>
  );
}

function PlatformDot({ platform }: { platform: string | null }) {
  return (
    <span
      className="inline-block size-2 rounded-full"
      style={{ background: platformColor(platform) }}
    />
  );
}

function platformColor(platform: string | null): string {
  const p = (platform ?? "").toLowerCase();
  if (p.includes("mikrotik")) return "#2563eb";
  if (p.includes("cisco")) return "#0891b2";
  if (p.includes("ubiquiti") || p.includes("uisp") || p.includes("unifi"))
    return "#16a34a";
  if (p.includes("aruba") || p.includes("hpe")) return "#ea580c";
  if (p.includes("juniper")) return "#7c3aed";
  if (p.includes("fortigate") || p.includes("fortinet")) return "#dc2626";
  return "#64748b";
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

// ---------------- Interfaces ----------------

function InterfacesTab({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data, isLoading, error } = useQuery<Interface[]>({
    queryKey: ["interfaces", deviceId],
    queryFn: () => listInterfaces(deviceId),
  });
  // Membership is a 1:N join (one physical interface in many lists),
  // so we fetch it alongside and build the lookup once per render.
  const { data: members } = useQuery<InterfaceListMember[]>({
    queryKey: ["interface-list-members", deviceId],
    queryFn: () => listInterfaceListMembers(deviceId),
  });
  const listsByInterface = useMemo(() => {
    const m = new Map<string, InterfaceListMember[]>();
    for (const row of members ?? []) {
      const existing = m.get(row.interface) ?? [];
      existing.push(row);
      m.set(row.interface, existing);
    }
    return m;
  }, [members]);

  const reset = useMutation({
    mutationFn: (name: string) => resetInterfaceCounters(deviceId, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["interfaces", deviceId] });
      toast.success("Counters reset");
    },
    onError: (e: Error) => toast.error("Reset failed", e.message),
  });

  return (
    <Section title="Interfaces" subtitle="All interfaces with link state and counters. Click Reset to zero rx/tx.">
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
              <th className="px-3 py-2 font-medium">Lists</th>
              <th className="px-3 py-2 font-medium">Comment</th>
              <th className="px-3 py-2 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && <EmptyRow colSpan={10} label="Loading…" />}
            {!isLoading && (!data || data.length === 0) && (
              <EmptyRow colSpan={10} label="No interfaces." />
            )}
            {data?.map((i) => {
              const memberships = listsByInterface.get(i.name) ?? [];
              return (
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
                  <td className="px-3 py-2">
                    {memberships.length === 0 ? (
                      <span className="text-[10px] text-muted-foreground/60">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {memberships.map((m) => (
                          <span
                            key={`${m.list}-${m.id ?? m.interface}`}
                            title={
                              m.dynamic
                                ? "Dynamic membership — comes from include/exclude rules on the list"
                                : m.disabled
                                  ? "Membership row is disabled"
                                  : `Manually added to list "${m.list}"`
                            }
                            className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium ${
                              m.disabled
                                ? "bg-zinc-100 text-zinc-500 line-through"
                                : m.dynamic
                                  ? "bg-blue-50 text-blue-700 ring-1 ring-blue-200"
                                  : "bg-indigo-100 text-indigo-800"
                            }`}
                          >
                            {m.list}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{i.comment ?? "—"}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => reset.mutate(i.name)}
                      disabled={reset.isPending}
                      className="text-xs text-muted-foreground hover:underline disabled:opacity-50"
                      title="Zero rx/tx counters on this interface"
                    >
                      Reset
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ErrorOrTable>
    </Section>
  );
}

// ---------------- Interface lists ----------------

function InterfaceListsTab({ deviceId }: { deviceId: string }) {
  const { data: lists, isLoading: listsLoading, error: listsError } = useQuery<
    InterfaceList[]
  >({
    queryKey: ["interface-lists", deviceId],
    queryFn: () => listInterfaceLists(deviceId),
  });
  const { data: members, error: memberError } = useQuery<InterfaceListMember[]>({
    queryKey: ["interface-list-members", deviceId],
    queryFn: () => listInterfaceListMembers(deviceId),
  });

  // Index members by list name so each card can render its own
  // interface chips without rescanning the full membership list.
  const membersByList = useMemo(() => {
    const m = new Map<string, InterfaceListMember[]>();
    for (const row of members ?? []) {
      const existing = m.get(row.list) ?? [];
      existing.push(row);
      m.set(row.list, existing);
    }
    return m;
  }, [members]);

  const sortedLists = useMemo(
    () => [...(lists ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [lists],
  );

  return (
    <Section
      title="Interface lists"
      subtitle="Named groups used in firewall rules, routing marks and discovery scope. Includes built-in lists like all, dynamic and none."
    >
      {(listsError || memberError) && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(listsError ?? memberError)?.message}
        </div>
      )}
      {listsLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {!listsLoading && sortedLists.length === 0 && !listsError && (
        <p className="text-sm text-muted-foreground">No interface lists yet.</p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {sortedLists.map((lst) => {
          const rows = membersByList.get(lst.name) ?? [];
          return (
            <div
              key={lst.id ?? lst.name}
              className="rounded-lg border border-border bg-card p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{lst.name}</h3>
                    {lst.builtin && (
                      <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-700">
                        built-in
                      </span>
                    )}
                    {lst.dynamic && !lst.builtin && (
                      <span className="rounded-md bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700 ring-1 ring-blue-200">
                        dynamic
                      </span>
                    )}
                  </div>
                  {lst.comment && (
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {lst.comment}
                    </p>
                  )}
                </div>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {rows.length} member{rows.length === 1 ? "" : "s"}
                </span>
              </div>
              {(lst.include || lst.exclude) && (
                <div className="mt-2 space-y-0.5 text-[11px] text-muted-foreground">
                  {lst.include && (
                    <div>
                      <span className="font-mono text-foreground/70">include:</span>{" "}
                      {lst.include}
                    </div>
                  )}
                  {lst.exclude && (
                    <div>
                      <span className="font-mono text-foreground/70">exclude:</span>{" "}
                      {lst.exclude}
                    </div>
                  )}
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-1">
                {rows.length === 0 ? (
                  <span className="text-[11px] italic text-muted-foreground/70">
                    No interfaces in this list.
                  </span>
                ) : (
                  rows.map((m) => (
                    <span
                      key={`${m.id ?? m.interface}-${m.interface}`}
                      title={
                        m.dynamic
                          ? "Dynamic — matched via include/exclude, not a manual entry"
                          : m.disabled
                            ? "Disabled member row"
                            : "Manual member"
                      }
                      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[11px] ${
                        m.disabled
                          ? "bg-zinc-100 text-zinc-500 line-through"
                          : m.dynamic
                            ? "bg-blue-50 text-blue-700 ring-1 ring-blue-200"
                            : "bg-indigo-100 text-indigo-800"
                      }`}
                    >
                      {m.interface}
                    </span>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
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
