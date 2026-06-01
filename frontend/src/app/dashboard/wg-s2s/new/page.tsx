"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import { listDevices, type Device } from "@/lib/devices";
import {
  listWgEndpointSuggestions,
  listWgLanSubnets,
  type WgEndpointSuggestion,
  type WgSubnetSuggestion,
} from "@/lib/vpn";
import {
  createSiteToSite,
  type S2SCreateResponse,
} from "@/lib/wg-s2s";

type Step = "pick" | "addressing" | "subnets" | "firewall" | "review" | "done";

const STEPS: { id: Step; label: string }[] = [
  { id: "pick", label: "Devices" },
  { id: "addressing", label: "Addressing" },
  { id: "subnets", label: "Networks" },
  { id: "firewall", label: "Firewall" },
  { id: "review", label: "Review" },
];

export default function S2SWizardPage() {
  const toast = useToast();
  const [step, setStep] = useState<Step>("pick");

  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });

  const [deviceAId, setDeviceAId] = useState<string>("");
  const [deviceBId, setDeviceBId] = useState<string>("");

  const [tunnelBase, setTunnelBase] = useState("10.99.0");
  const [prefix, setPrefix] = useState(30);
  const tunnelCidrA = `${tunnelBase}.1/${prefix}`;
  const tunnelCidrB = `${tunnelBase}.2/${prefix}`;

  const [ifaceA, setIfaceA] = useState("wg-to-b");
  const [ifaceB, setIfaceB] = useState("wg-to-a");
  const [listenPort, setListenPort] = useState(51820);
  const [publicEndpoint, setPublicEndpoint] = useState("");
  const [commentTag, setCommentTag] = useState("site-to-site-1");
  const [keepalive, setKeepalive] = useState(25);

  const [exposeA, setExposeA] = useState<Set<string>>(new Set());
  const [exposeB, setExposeB] = useState<Set<string>>(new Set());
  const [extraExposeA, setExtraExposeA] = useState("");
  const [extraExposeB, setExtraExposeB] = useState("");

  const [openFirewallA, setOpenFirewallA] = useState(true);
  const [createForwardRules, setCreateForwardRules] = useState(true);

  const deviceA = devices?.find((d) => d.id === deviceAId);
  const deviceB = devices?.find((d) => d.id === deviceBId);

  const { data: aSubnets } = useQuery<WgSubnetSuggestion[]>({
    queryKey: ["wg-lan-subnets", deviceAId],
    queryFn: () => listWgLanSubnets(deviceAId),
    enabled: Boolean(deviceAId),
  });
  const { data: bSubnets } = useQuery<WgSubnetSuggestion[]>({
    queryKey: ["wg-lan-subnets", deviceBId],
    queryFn: () => listWgLanSubnets(deviceBId),
    enabled: Boolean(deviceBId),
  });
  const { data: aEndpoints } = useQuery<WgEndpointSuggestion[]>({
    queryKey: ["wg-endpoint-suggestions", deviceAId],
    queryFn: () => listWgEndpointSuggestions(deviceAId),
    enabled: Boolean(deviceAId),
  });

  useEffect(() => {
    if (!publicEndpoint && aEndpoints && aEndpoints.length > 0) {
      setPublicEndpoint(aEndpoints[0].address);
    }
  }, [aEndpoints, publicEndpoint]);

  const finalExposeA = useMemo(
    () => mergeCidrs(Array.from(exposeA), extraExposeA),
    [exposeA, extraExposeA],
  );
  const finalExposeB = useMemo(
    () => mergeCidrs(Array.from(exposeB), extraExposeB),
    [exposeB, extraExposeB],
  );

  const apply = useMutation<S2SCreateResponse>({
    mutationFn: () =>
      createSiteToSite({
        a: {
          device_id: deviceAId,
          interface_name: ifaceA,
          tunnel_cidr: tunnelCidrA,
          expose_subnets: finalExposeA,
        },
        b: {
          device_id: deviceBId,
          interface_name: ifaceB,
          tunnel_cidr: tunnelCidrB,
          expose_subnets: finalExposeB,
        },
        listen_port: listenPort,
        public_endpoint: publicEndpoint,
        comment_tag: commentTag,
        open_firewall_on_a: openFirewallA,
        create_forward_rules: createForwardRules,
        persistent_keepalive: keepalive,
      }),
    onSuccess: () => {
      toast.success(
        "Tunnel up",
        `Tagged netfleet s2s ${commentTag} on both routers`,
      );
      setStep("done");
    },
    onError: (e: Error) => toast.error("Apply failed", e.message),
  });

  const canAdvance = (s: Step): boolean => {
    if (s === "pick") return !!deviceAId && !!deviceBId && deviceAId !== deviceBId;
    if (s === "addressing")
      return (
        !!ifaceA.trim() &&
        !!ifaceB.trim() &&
        !!tunnelBase.trim() &&
        !!publicEndpoint.trim() &&
        listenPort > 0
      );
    return true;
  };

  return (
    <div>
      <Link
        href="/dashboard/fleet"
        className="text-xs text-muted-foreground hover:underline"
      >
        ← Fleet
      </Link>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">
        Site-to-site WireGuard tunnel
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Connect two MikroTik routers so each can reach the LAN behind the
        other. The wizard provisions the interfaces, addresses, peers and the
        firewall rules in one apply.
      </p>

      <ol className="mt-6 flex flex-wrap gap-1 text-xs">
        {STEPS.map((s, i) => {
          const active = s.id === step;
          const done =
            STEPS.findIndex((x) => x.id === step) > i && step !== "done";
          return (
            <li
              key={s.id}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 ${
                active
                  ? "bg-primary/10 text-primary"
                  : done
                    ? "bg-muted text-muted-foreground"
                    : "bg-muted/40 text-muted-foreground"
              }`}
            >
              <span className="font-mono">{i + 1}</span> · {s.label}
              {done && <span>✓</span>}
            </li>
          );
        })}
      </ol>

      <div className="mt-6">
        {step === "pick" && (
          <Section title="Pick the two routers">
            <div className="grid gap-4 md:grid-cols-2">
              <DevicePick
                label="Device A · listener"
                value={deviceAId}
                onChange={setDeviceAId}
                devices={devices ?? []}
                excludeId={deviceBId}
              />
              <DevicePick
                label="Device B · dial-out"
                value={deviceBId}
                onChange={setDeviceBId}
                devices={devices ?? []}
                excludeId={deviceAId}
              />
            </div>
            <p className="mt-3 text-[11px] text-muted-foreground">
              Device A keeps a UDP listener open and is what Device B dials.
              Pick the one with a public IP / DDNS as A.
            </p>
            <NextButton
              disabled={!canAdvance("pick")}
              onClick={() => setStep("addressing")}
            />
          </Section>
        )}

        {step === "addressing" && (
          <Section title="Tunnel addressing">
            <div className="grid gap-4 md:grid-cols-2">
              <LabelGroup label={`Interface on ${deviceA?.name ?? "A"}`}>
                <input
                  value={ifaceA}
                  onChange={(e) => setIfaceA(e.target.value)}
                  className={input}
                />
              </LabelGroup>
              <LabelGroup label={`Interface on ${deviceB?.name ?? "B"}`}>
                <input
                  value={ifaceB}
                  onChange={(e) => setIfaceB(e.target.value)}
                  className={input}
                />
              </LabelGroup>
              <LabelGroup label="Tunnel network (first three octets)">
                <input
                  value={tunnelBase}
                  onChange={(e) => setTunnelBase(e.target.value)}
                  className={`${input} font-mono`}
                  placeholder="10.99.0"
                />
                <p className="text-[11px] italic text-muted-foreground">
                  A: {tunnelCidrA} · B: {tunnelCidrB}
                </p>
              </LabelGroup>
              <LabelGroup label="Prefix">
                <select
                  value={prefix}
                  onChange={(e) => setPrefix(Number(e.target.value))}
                  className={input}
                >
                  <option value={30}>/30 (point-to-point)</option>
                  <option value={29}>/29</option>
                  <option value={24}>/24</option>
                </select>
              </LabelGroup>
              <LabelGroup label="Listen port on A">
                <input
                  type="number"
                  min={1}
                  max={65535}
                  value={listenPort}
                  onChange={(e) => setListenPort(Number(e.target.value))}
                  className={input}
                />
              </LabelGroup>
              <LabelGroup label="Persistent keepalive (s)">
                <input
                  type="number"
                  min={0}
                  max={65535}
                  value={keepalive}
                  onChange={(e) => setKeepalive(Number(e.target.value))}
                  className={input}
                />
              </LabelGroup>
              <LabelGroup label={`Public endpoint of ${deviceA?.name ?? "A"}`}>
                <input
                  value={publicEndpoint}
                  onChange={(e) => setPublicEndpoint(e.target.value)}
                  className={input}
                  list="s2s-ep"
                  placeholder="router-a.example.com"
                />
                {aEndpoints && (
                  <datalist id="s2s-ep">
                    {aEndpoints.map((e) => (
                      <option key={e.address} value={e.address}>
                        {e.interface}
                      </option>
                    ))}
                  </datalist>
                )}
                {aEndpoints && aEndpoints.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {aEndpoints.map((e) => (
                      <button
                        type="button"
                        key={e.address}
                        onClick={() => setPublicEndpoint(e.address)}
                        className={`rounded-md border px-2 py-0.5 text-[11px] font-mono transition hover:bg-accent ${
                          publicEndpoint === e.address
                            ? "border-primary bg-primary/5 text-primary"
                            : "border-input bg-background text-muted-foreground"
                        }`}
                      >
                        {e.address}{" "}
                        <span className="text-muted-foreground">· {e.interface}</span>
                      </button>
                    ))}
                  </div>
                )}
              </LabelGroup>
              <LabelGroup label="Comment tag (sticks to every row written)">
                <input
                  value={commentTag}
                  onChange={(e) => setCommentTag(e.target.value)}
                  className={input}
                  placeholder="site-corp-to-branch"
                />
              </LabelGroup>
            </div>
            <NavRow
              onBack={() => setStep("pick")}
              onNext={() => setStep("subnets")}
              nextDisabled={!canAdvance("addressing")}
            />
          </Section>
        )}

        {step === "subnets" && (
          <Section title="Which networks should the other side see?">
            <p className="text-xs text-muted-foreground">
              Ticked subnets get added to the remote peer&apos;s AllowedIPs,
              which on RouterOS doubles as a route. Pick only what the other
              side genuinely needs — anything else stays unreachable.
            </p>
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              <SubnetPanel
                title={`${deviceA?.name ?? "A"} → expose to B`}
                subnets={aSubnets ?? []}
                picks={exposeA}
                onToggle={(c, on) => setExposeA(togglePicks(exposeA, c, on))}
                extra={extraExposeA}
                onExtra={setExtraExposeA}
              />
              <SubnetPanel
                title={`${deviceB?.name ?? "B"} → expose to A`}
                subnets={bSubnets ?? []}
                picks={exposeB}
                onToggle={(c, on) => setExposeB(togglePicks(exposeB, c, on))}
                extra={extraExposeB}
                onExtra={setExtraExposeB}
              />
            </div>
            <NavRow
              onBack={() => setStep("addressing")}
              onNext={() => setStep("firewall")}
            />
          </Section>
        )}

        {step === "firewall" && (
          <Section title="Firewall">
            <label className="flex items-start gap-2 rounded-md border border-border bg-muted/30 p-3">
              <input
                type="checkbox"
                checked={openFirewallA}
                onChange={(e) => setOpenFirewallA(e.target.checked)}
                className="mt-0.5 size-4 rounded"
              />
              <span className="text-sm">
                <span className="font-medium">
                  Open UDP/{listenPort} on {deviceA?.name ?? "A"}
                </span>
                <span className="ml-1 text-xs text-muted-foreground">
                  Adds an <span className="font-mono">accept</span> rule at the
                  top of the input chain so the handshake completes.
                </span>
              </span>
            </label>
            <label className="mt-3 flex items-start gap-2 rounded-md border border-border bg-muted/30 p-3">
              <input
                type="checkbox"
                checked={createForwardRules}
                onChange={(e) => setCreateForwardRules(e.target.checked)}
                className="mt-0.5 size-4 rounded"
              />
              <span className="text-sm">
                <span className="font-medium">
                  Create forward-chain accept rules on both routers
                </span>
                <span className="ml-1 text-xs text-muted-foreground">
                  Two rules per side (in-interface / out-interface = the wg
                  interface). Required when the forward chain has a catch-all
                  drop at the bottom.
                </span>
              </span>
            </label>
            <NavRow
              onBack={() => setStep("subnets")}
              onNext={() => setStep("review")}
            />
          </Section>
        )}

        {step === "review" && (
          <Section title="Review and apply">
            <div className="grid gap-4 md:grid-cols-2">
              <SummaryCard
                title={`${deviceA?.name ?? "A"} (listener)`}
                rows={[
                  ["Interface", ifaceA],
                  ["Tunnel address", tunnelCidrA],
                  ["Listen port", String(listenPort)],
                  ["Endpoint", publicEndpoint],
                  ["Exposes to B", finalExposeA.join(", ") || "—"],
                ]}
              />
              <SummaryCard
                title={`${deviceB?.name ?? "B"} (dial-out)`}
                rows={[
                  ["Interface", ifaceB],
                  ["Tunnel address", tunnelCidrB],
                  ["Keepalive", `${keepalive}s`],
                  ["Exposes to A", finalExposeB.join(", ") || "—"],
                ]}
              />
            </div>
            <div className="mt-4 rounded-md border border-border bg-muted/30 p-3 text-xs">
              <div>
                <span className="font-semibold">Open UDP on A:</span>{" "}
                {openFirewallA ? "yes" : "no"}
              </div>
              <div>
                <span className="font-semibold">Forward accept rules:</span>{" "}
                {createForwardRules ? "yes (2 per side)" : "no"}
              </div>
              <div>
                <span className="font-semibold">Comment tag:</span>{" "}
                <span className="font-mono">netfleet s2s {commentTag}</span>
              </div>
            </div>
            <NavRow
              onBack={() => setStep("firewall")}
              onNext={() => apply.mutate()}
              nextLabel={apply.isPending ? "Applying…" : "Apply"}
              nextDisabled={apply.isPending}
            />
            {apply.error && (
              <pre className="mt-3 overflow-auto rounded-md border border-destructive/40 bg-destructive/10 p-3 text-[11px] text-destructive">
                {(apply.error as Error).message}
              </pre>
            )}
          </Section>
        )}

        {step === "done" && apply.data && (
          <Section title="Tunnel created">
            <p className="text-sm text-emerald-700">
              {apply.data.artifacts.length} object
              {apply.data.artifacts.length === 1 ? "" : "s"} written. Use the
              comment tag{" "}
              <span className="font-mono">netfleet s2s {apply.data.comment_tag}</span>{" "}
              to find them later.
            </p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="rounded-md border border-border bg-card p-3 text-xs">
                <div className="font-semibold">{deviceA?.name ?? "A"}</div>
                <ul className="mt-1 space-y-0.5">
                  {apply.data.artifacts
                    .filter((a) => a.side === "a")
                    .map((a, i) => (
                      <li key={`a-${i}`} className="font-mono">
                        {a.kind}: {a.detail ?? a.id}
                      </li>
                    ))}
                </ul>
              </div>
              <div className="rounded-md border border-border bg-card p-3 text-xs">
                <div className="font-semibold">{deviceB?.name ?? "B"}</div>
                <ul className="mt-1 space-y-0.5">
                  {apply.data.artifacts
                    .filter((a) => a.side === "b")
                    .map((a, i) => (
                      <li key={`b-${i}`} className="font-mono">
                        {a.kind}: {a.detail ?? a.id}
                      </li>
                    ))}
                </ul>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Link
                href={`/dashboard/devices/${deviceAId}/vpn/wireguard`}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
              >
                Open {deviceA?.name ?? "A"} WG
              </Link>
              <Link
                href={`/dashboard/devices/${deviceBId}/vpn/wireguard`}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
              >
                Open {deviceB?.name ?? "B"} WG
              </Link>
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

// ---------------- helpers ----------------

function togglePicks(set: Set<string>, val: string, on: boolean): Set<string> {
  const next = new Set(set);
  if (on) next.add(val);
  else next.delete(val);
  return next;
}

function mergeCidrs(picks: string[], extra: string): string[] {
  const seen = new Set(picks);
  for (const c of extra.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean)) {
    seen.add(c);
  }
  return Array.from(seen);
}

// ---------------- presentation ----------------

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function DevicePick({
  label,
  value,
  onChange,
  devices,
  excludeId,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  devices: Device[];
  excludeId: string;
}) {
  return (
    <label className="block space-y-1 text-sm font-medium">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={input}
      >
        <option value="">— pick a device —</option>
        {devices
          .filter((d) => d.id !== excludeId && d.vendor === "mikrotik")
          .map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} · {d.host}
            </option>
          ))}
      </select>
    </label>
  );
}

function LabelGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1 text-sm font-medium">
      {label}
      {children}
    </label>
  );
}

function SubnetPanel({
  title,
  subnets,
  picks,
  onToggle,
  extra,
  onExtra,
}: {
  title: string;
  subnets: WgSubnetSuggestion[];
  picks: Set<string>;
  onToggle: (cidr: string, on: boolean) => void;
  extra: string;
  onExtra: (v: string) => void;
}) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="text-sm font-medium">{title}</div>
      <div className="mt-2 space-y-1 text-xs">
        {subnets.length === 0 ? (
          <p className="italic text-muted-foreground">
            No LAN subnets discovered.
          </p>
        ) : (
          subnets.map((s) => (
            <label key={s.cidr} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={picks.has(s.cidr)}
                onChange={(e) => onToggle(s.cidr, e.target.checked)}
                className="size-4"
              />
              <span className="font-mono">{s.cidr}</span>
              <span className="text-muted-foreground">· {s.interface}</span>
            </label>
          ))
        )}
      </div>
      <label className="mt-3 block text-[11px]">
        Extra CIDRs
        <input
          value={extra}
          onChange={(e) => onExtra(e.target.value)}
          className={`${input} mt-1 font-mono`}
          placeholder="172.16.0.0/12"
        />
      </label>
    </div>
  );
}

function SummaryCard({
  title,
  rows,
}: {
  title: string;
  rows: [string, string][];
}) {
  return (
    <div className="rounded-md border border-border bg-card p-3 text-sm">
      <div className="font-semibold">{title}</div>
      <dl className="mt-2 grid grid-cols-[7rem_1fr] gap-y-1 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="font-mono">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function NextButton({
  disabled,
  onClick,
}: {
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <div className="mt-4 flex justify-end">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
      >
        Continue
      </button>
    </div>
  );
}

function NavRow({
  onBack,
  onNext,
  nextLabel = "Continue",
  nextDisabled,
}: {
  onBack: () => void;
  onNext: () => void;
  nextLabel?: string;
  nextDisabled?: boolean;
}) {
  return (
    <div className="mt-4 flex justify-between">
      <button
        type="button"
        onClick={onBack}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
      >
        ← Back
      </button>
      <button
        type="button"
        onClick={onNext}
        disabled={nextDisabled}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
      >
        {nextLabel}
      </button>
    </div>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";
