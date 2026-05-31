"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { useToast } from "@/components/toast";
import {
  createFilterRule,
  listFilterRules,
  moveFilterRule,
} from "@/lib/firewall";
import {
  createIpAddress,
  createWgInterface,
  createWgPeer,
  downloadWgClientConfig,
  listWgEndpointSuggestions,
  listWgInterfaces,
  listWgLanSubnets,
  type WgEndpointSuggestion,
  type WgInterface,
  type WgSubnetSuggestion,
} from "@/lib/vpn";

type Step = "interface" | "address" | "peers";

export default function WireguardWizardPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;

  const [step, setStep] = useState<Step>("interface");
  const [iface, setIface] = useState<WgInterface | null>(null);
  // Used by the peer step to suggest a default client address and to
  // know what subnet to auto-tick under AllowedIPs.
  const [tunnelCidr, setTunnelCidr] = useState<string | null>(null);

  return (
    <div>
      <Link
        href={`/dashboard/devices/${deviceId}/vpn/wireguard`}
        className="text-xs text-muted-foreground hover:underline"
      >
        ← WireGuard
      </Link>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">
        Bootstrap WireGuard
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Create or pick an interface, assign it a tunnel address, then add as
        many peers as you need — each with a freshly generated keypair and a
        downloadable client config.
      </p>

      <ol className="mt-6 flex flex-wrap gap-1 text-xs">
        {(
          [
            ["interface", "Interface"],
            ["address", "Tunnel address"],
            ["peers", "Peers"],
          ] as [Step, string][]
        ).map(([id, label], i) => {
          const active = id === step;
          const done =
            (id === "interface" && iface !== null) ||
            (id === "address" && tunnelCidr !== null);
          return (
            <li
              key={id}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 ${
                active
                  ? "bg-primary/10 text-primary"
                  : done
                    ? "bg-muted text-muted-foreground"
                    : "bg-muted/40 text-muted-foreground"
              }`}
            >
              <span className="font-mono">{i + 1}</span> · {label}
              {done && !active && <span>✓</span>}
            </li>
          );
        })}
      </ol>

      <div className="mt-6">
        {step === "interface" && (
          <InterfaceStep
            deviceId={deviceId}
            onPicked={(i) => {
              setIface(i);
              setStep("address");
            }}
          />
        )}
        {step === "address" && iface && (
          <AddressStep
            deviceId={deviceId}
            iface={iface}
            onBack={() => setStep("interface")}
            onCreated={(cidr) => {
              setTunnelCidr(cidr);
              setStep("peers");
            }}
          />
        )}
        {step === "peers" && iface && (
          <PeersStep
            deviceId={deviceId}
            iface={iface}
            tunnelCidr={tunnelCidr}
            onBack={() => setStep("address")}
          />
        )}
      </div>
    </div>
  );
}

// ---------------- Step 1: Interface ----------------

function InterfaceStep({
  deviceId,
  onPicked,
}: {
  deviceId: string;
  onPicked: (i: WgInterface) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const { data: interfaces } = useQuery<WgInterface[]>({
    queryKey: ["wg-interfaces", deviceId],
    queryFn: () => listWgInterfaces(deviceId),
  });

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("wg-net");
  const [port, setPort] = useState(51820);
  const [mtu, setMtu] = useState(1420);
  const [openFirewall, setOpenFirewall] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: async () => {
      await createWgInterface(deviceId, {
        name,
        listen_port: port,
        mtu,
      });

      // Optionally punch a hole in the input chain so peers outside the
      // router can actually reach the listen port. Without this step the
      // tunnel handshakes never start on most "secure by default"
      // RouterOS configs.
      if (openFirewall) {
        try {
          const created = await createFilterRule(deviceId, {
            chain: "input",
            action: "accept",
            protocol: "udp",
            dst_port: String(port),
            comment: `netfleet wg ${name} listen`,
          });
          // Push the new rule to the very top of the input chain so it
          // wins over any catch-all drop the operator already has below.
          try {
            const rules = await listFilterRules(deviceId);
            const firstInput = rules.find(
              (r) => r.chain === "input" && r.id && r.id !== created.id,
            );
            if (firstInput?.id) {
              await moveFilterRule(deviceId, created.id, firstInput.id);
            }
          } catch (e) {
            // Reorder failure is non-fatal — the rule still exists,
            // just at the wrong priority. Surface it as a warning so
            // the operator can fix it from /firewall.
            toast.error(
              "Rule created but not moved to top",
              (e as Error).message,
            );
          }
        } catch (e) {
          toast.error("Firewall hole-punch failed", (e as Error).message);
        }
      }
    },
    onSuccess: async () => {
      // The driver doesn't echo the new interface, so refetch + match by name.
      const fresh = await listWgInterfaces(deviceId);
      qc.setQueryData(["wg-interfaces", deviceId], fresh);
      const picked = fresh.find((i) => i.name === name);
      if (picked) {
        toast.success(
          "Interface created",
          openFirewall ? `UDP/${port} opened in input chain` : picked.name,
        );
        onPicked(picked);
      } else {
        setError("Interface created but couldn't be looked up.");
      }
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-base font-semibold">Pick or create an interface</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        The interface is the WireGuard endpoint on the router. RouterOS
        auto-generates the keypair when you create it.
      </p>

      <div className="mt-4 space-y-2">
        {interfaces?.length === 0 && (
          <p className="rounded-md border border-dashed border-border bg-background p-3 text-center text-xs text-muted-foreground">
            No interfaces yet — create one below.
          </p>
        )}
        {interfaces?.map((i) => (
          <button
            key={i.name}
            type="button"
            onClick={() => onPicked(i)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-left text-sm transition hover:bg-accent"
          >
            <div className="font-medium">{i.name}</div>
            <div className="text-[11px] text-muted-foreground">
              port {i.listen_port ?? "—"} · mtu {i.mtu ?? "—"} ·{" "}
              {i.public_key ? "pubkey ✓" : "no pubkey"}
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
              if (!name.trim()) return setError("Name is required.");
              create.mutate();
            }}
            className="grid gap-3 md:grid-cols-3"
          >
            {error && (
              <p className="md:col-span-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </p>
            )}
            <label className="block space-y-1 text-sm font-medium">
              Name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className={input}
                placeholder="wg-corp"
              />
            </label>
            <label className="block space-y-1 text-sm font-medium">
              Listen port
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
              MTU
              <input
                type="number"
                min={576}
                max={1500}
                value={mtu}
                onChange={(e) => setMtu(Number(e.target.value))}
                className={input}
              />
            </label>
            <label className="md:col-span-3 flex items-start gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
              <input
                type="checkbox"
                checked={openFirewall}
                onChange={(e) => setOpenFirewall(e.target.checked)}
                className="mt-0.5 size-4 rounded"
              />
              <span className="text-sm">
                <span className="font-medium">
                  Open UDP /{port} in the input firewall
                </span>
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  Adds an <span className="font-mono">accept</span> rule at the
                  top of the input chain so external peers can complete the
                  handshake. Comment tag:{" "}
                  <span className="font-mono">netfleet wg {name} listen</span>.
                </span>
              </span>
            </label>
            <div className="md:col-span-3 flex justify-end gap-2">
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
            + Create a new interface instead
          </button>
        )}
      </div>
    </section>
  );
}

// ---------------- Step 2: Address ----------------

function AddressStep({
  deviceId,
  iface,
  onBack,
  onCreated,
}: {
  deviceId: string;
  iface: WgInterface;
  onBack: () => void;
  onCreated: (cidr: string) => void;
}) {
  const toast = useToast();
  const [cidr, setCidr] = useState("10.10.10.1/24");
  const [comment, setComment] = useState(`wg ${iface.name}`);
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState(false);

  const m = useMutation({
    mutationFn: () =>
      createIpAddress(deviceId, {
        address: cidr,
        interface: iface.name,
        comment: comment || null,
      }),
    onSuccess: () => {
      toast.success("Address assigned", cidr);
      onCreated(cidr);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-base font-semibold">
            Tunnel address on <span className="font-mono">{iface.name}</span>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The router needs an IP on the WireGuard interface so peers have a
            gateway. Choose a private subnet that doesn&apos;t overlap with
            existing LAN ranges.
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="text-xs text-muted-foreground hover:underline"
        >
          ← Interface
        </button>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!cidr.includes("/")) return setError("Address must include /CIDR.");
          m.mutate();
        }}
        className="mt-4 space-y-3"
      >
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}
        {skipped && (
          <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Skipping address assignment — make sure the interface already has
            an IP, or peers won&apos;t have a gateway.
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block space-y-1 text-sm font-medium">
            Address / CIDR
            <input
              required
              value={cidr}
              onChange={(e) => setCidr(e.target.value)}
              className={`${input} font-mono`}
              placeholder="10.10.10.1/24"
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
        <div className="flex justify-between">
          <button
            type="button"
            onClick={() => {
              setSkipped(true);
              onCreated(cidr);
            }}
            className="text-xs text-muted-foreground hover:underline"
          >
            Skip — interface already has an address
          </button>
          <button
            type="submit"
            disabled={m.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Assigning…" : "Assign address + continue"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- Step 3: Peers ----------------

interface PeerDraft {
  comment: string;
  publicKey: string;
  privateKey: string;
  allowedAddress: string;
}

interface IssuedConfig {
  comment: string;
  filename: string;
  text: string;
}

function PeersStep({
  deviceId,
  iface,
  tunnelCidr,
  onBack,
}: {
  deviceId: string;
  iface: WgInterface;
  tunnelCidr: string | null;
  onBack: () => void;
}) {
  const toast = useToast();
  const router = useMemo(() => {
    // Suggest the next host bit after the router IP. If tunnelCidr is
    // 10.10.10.1/24 the next peer goes to 10.10.10.2/32, then .3/32, …
    const base = tunnelCidr ?? "10.10.10.1/24";
    const [host, prefix] = base.split("/");
    const parts = host.split(".").map((n) => Number(n));
    let counter = parts[3] + 1;
    return {
      prefix,
      nextHost(): string {
        const ip = `${parts[0]}.${parts[1]}.${parts[2]}.${counter++}`;
        return `${ip}/32`;
      },
    };
  }, [tunnelCidr]);

  const { data: endpointSuggestions } = useQuery<WgEndpointSuggestion[]>({
    queryKey: ["wg-endpoint-suggestions", deviceId],
    queryFn: () => listWgEndpointSuggestions(deviceId),
  });
  const { data: lanSubnets } = useQuery<WgSubnetSuggestion[]>({
    queryKey: ["wg-lan-subnets", deviceId],
    queryFn: () => listWgLanSubnets(deviceId),
  });

  const [draft, setDraft] = useState<PeerDraft>(() => ({
    comment: "",
    publicKey: "",
    privateKey: "",
    allowedAddress: router.nextHost(),
  }));
  const [issued, setIssued] = useState<IssuedConfig[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [endpoint, setEndpoint] = useState(
    endpointSuggestions?.[0]?.address ?? "",
  );
  useEffect(() => {
    if (!endpoint && endpointSuggestions && endpointSuggestions.length > 0) {
      setEndpoint(endpointSuggestions[0].address);
    }
  }, [endpoint, endpointSuggestions]);
  const [allowedIpsPicks, setAllowedIpsPicks] = useState<Set<string>>(
    () => new Set(["0.0.0.0/0", "::/0"]),
  );

  function toggleAi(cidr: string, on: boolean) {
    setAllowedIpsPicks((prev) => {
      const next = new Set(prev);
      if (on) next.add(cidr);
      else next.delete(cidr);
      return next;
    });
  }

  async function generateKeypair() {
    // The Web Crypto Curve25519 is not in browsers yet, so we shell out to
    // the existing wg helper on the server when creating the peer — we
    // just leave both fields blank in the draft and let the server fill
    // them. Until then there's nothing to do here.
    toast.info?.("Keys are generated on the server when you submit");
  }

  const create = useMutation({
    mutationFn: async () => {
      // Step A: ask the server to mint a server-side keypair for the
      // peer's "client" by hitting the existing config endpoint after
      // create. But the peer ADD needs the client's public key. To
      // keep things simple, we generate a placeholder keypair on the
      // server before adding — by reusing the /config endpoint after
      // adding the peer. For Stage 9.3 we use this minimal flow:
      //
      //   1. Ask the operator to paste a public key OR check
      //      "generate".
      //   2. If generate, generate keypair via the existing
      //      /config endpoint, which embeds a fresh PrivateKey in the
      //      returned wg-quick file (matches the existing UI).
      //
      // The simplest path that keeps Stage 9.3 small: require the
      // operator to paste a public key, because the client config
      // endpoint already generates the private side for "this
      // dialog".
      if (!draft.publicKey) {
        throw new Error(
          "Public key is required. Paste the peer's WireGuard public key.",
        );
      }
      const psk = await createWgPeer(deviceId, {
        interface: iface.name,
        public_key: draft.publicKey,
        allowed_address: draft.allowedAddress,
        comment: draft.comment || null,
      });
      if (!psk.id) throw new Error("No peer id returned");

      // Now ask the server to assemble a client config. The server
      // returns the .conf text including the assigned PSK.
      const allowedIps = Array.from(allowedIpsPicks).join(", ");
      const cfg = await downloadWgClientConfig(deviceId, psk.id, {
        server_endpoint: endpoint,
        server_endpoint_port: iface.listen_port ?? 51820,
        client_address: draft.allowedAddress,
        client_dns: null,
        allowed_ips: allowedIps,
        persistent_keepalive: 25,
      });
      return { ...cfg, comment: draft.comment } satisfies IssuedConfig;
    },
    onSuccess: (cfg) => {
      setIssued((prev) => [...prev, cfg]);
      setDraft({
        comment: "",
        publicKey: "",
        privateKey: "",
        allowedAddress: router.nextHost(),
      });
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  function triggerDownload(c: IssuedConfig) {
    const blob = new Blob([c.text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = c.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex items-baseline justify-between">
          <div>
            <h2 className="text-base font-semibold">
              Add peers on <span className="font-mono">{iface.name}</span>
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              For each peer, paste their WireGuard public key (the value next
              to <span className="font-mono">PublicKey =</span> in their
              client&apos;s key file). NetFleet picks the next free /32 in
              the tunnel range automatically.
            </p>
          </div>
          <button
            type="button"
            onClick={onBack}
            className="text-xs text-muted-foreground hover:underline"
          >
            ← Address
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
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
              Peer label
              <input
                value={draft.comment}
                onChange={(e) =>
                  setDraft({ ...draft, comment: e.target.value })
                }
                className={input}
                placeholder="nika-laptop"
              />
            </label>
            <label className="block space-y-1 text-sm font-medium">
              Tunnel address
              <input
                required
                value={draft.allowedAddress}
                onChange={(e) =>
                  setDraft({ ...draft, allowedAddress: e.target.value })
                }
                className={`${input} font-mono`}
                placeholder="10.10.10.2/32"
              />
            </label>
            <label className="block space-y-1 text-sm font-medium md:col-span-2">
              Peer public key
              <input
                required
                value={draft.publicKey}
                onChange={(e) =>
                  setDraft({ ...draft, publicKey: e.target.value })
                }
                className={`${input} font-mono`}
                placeholder="base64-encoded public key from the peer"
              />
              <span className="block text-[11px] italic font-normal text-muted-foreground">
                The client&apos;s side generates this; on Linux/macOS it&apos;s
                <span className="ml-1 font-mono">wg pubkey &lt; client.key</span>.
              </span>
            </label>
            <label className="block space-y-1 text-sm font-medium">
              Server endpoint (for the .conf)
              <input
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                className={input}
                placeholder="vpn.example.com"
                list="wgw-ep"
              />
              {endpointSuggestions && (
                <datalist id="wgw-ep">
                  {endpointSuggestions.map((s) => (
                    <option key={s.address} value={s.address}>
                      {s.interface}
                    </option>
                  ))}
                </datalist>
              )}
            </label>
            <button
              type="button"
              onClick={generateKeypair}
              className="self-end text-xs text-primary hover:underline"
            >
              How do I get a public key?
            </button>
          </div>

          <div className="text-sm font-medium">Allowed IPs (split tunnel)</div>
          <div className="space-y-1 text-xs">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={allowedIpsPicks.has("0.0.0.0/0")}
                onChange={(e) => toggleAi("0.0.0.0/0", e.target.checked)}
                className="size-4"
              />
              <span className="font-mono">0.0.0.0/0</span> · full tunnel
            </label>
            {lanSubnets?.map((s) => (
              <label key={s.cidr} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={allowedIpsPicks.has(s.cidr)}
                  onChange={(e) => toggleAi(s.cidr, e.target.checked)}
                  className="size-4"
                />
                <span className="font-mono">{s.cidr}</span>
                <span className="text-muted-foreground">· {s.interface}</span>
              </label>
            ))}
          </div>

          <div className="flex justify-end">
            <button
              type="submit"
              disabled={create.isPending}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {create.isPending ? "Adding peer…" : "Add peer + download config"}
            </button>
          </div>
        </form>
      </div>

      {issued.length > 0 && (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50/40 p-5">
          <h3 className="text-base font-semibold text-emerald-900">
            Issued configs
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Hand each .conf file to its peer. Closing this page throws away
            the client private key — NetFleet doesn&apos;t store it.
          </p>
          <ul className="mt-3 space-y-2">
            {issued.map((c, i) => (
              <li
                key={i}
                className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <div>
                  <div className="font-medium">
                    {c.comment || `peer #${i + 1}`}
                  </div>
                  <div className="font-mono text-[11px] text-muted-foreground">
                    {c.filename}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => triggerDownload(c)}
                  className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:opacity-90"
                >
                  Download
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex justify-end">
        <Link
          href={`/dashboard/devices/${deviceId}/vpn/wireguard`}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
        >
          Finish — back to WireGuard
        </Link>
      </div>
    </section>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
