"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import {
  createWgInterface,
  createWgPeer,
  deleteWgInterface,
  deleteWgPeer,
  downloadWgClientConfig,
  listWgEndpointSuggestions,
  listWgInterfaces,
  listWgLanSubnets,
  listWgPeers,
  restrictWgPeer,
  type WgEndpointSuggestion,
  type WgInterface,
  type WgPeer,
  type WgSubnetSuggestion,
} from "@/lib/vpn";

export default function WireguardPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const qc = useQueryClient();

  const { data: interfaces, isLoading: ifLoading, error: ifError } = useQuery<WgInterface[]>({
    queryKey: ["wg-interfaces", deviceId],
    queryFn: () => listWgInterfaces(deviceId),
  });
  const { data: peers, isLoading: peersLoading } = useQuery<WgPeer[]>({
    queryKey: ["wg-peers", deviceId],
    queryFn: () => listWgPeers(deviceId),
  });

  const [showIfForm, setShowIfForm] = useState(false);
  const [showPeerForm, setShowPeerForm] = useState(false);
  const [configFor, setConfigFor] = useState<WgPeer | null>(null);
  const [restrictFor, setRestrictFor] = useState<WgPeer | null>(null);
  const [createdPeerPsk, setCreatedPeerPsk] = useState<{ id: string; psk: string | null } | null>(
    null,
  );

  const delIf = useMutation({
    mutationFn: (id: string) => deleteWgInterface(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wg-interfaces", deviceId] }),
  });
  const delPeer = useMutation({
    mutationFn: (id: string) => deleteWgPeer(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wg-peers", deviceId] }),
  });

  return (
    <div className="space-y-10">
      <div className="flex justify-end">
        <Link
          href={`/dashboard/devices/${deviceId}/vpn/wireguard/new`}
          className="rounded-md border border-primary/40 bg-primary/5 px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/10"
        >
          ✨ Bootstrap WireGuard (interface → address → peers)
        </Link>
      </div>
      {/* ---------------- Interfaces ---------------- */}
      <section>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold">Interfaces</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Server-side WireGuard interfaces. Private key is generated server-side if you don&apos;t supply one.
            </p>
          </div>
          <button
            onClick={() => setShowIfForm((s) => !s)}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90"
          >
            {showIfForm ? "Cancel" : "+ New interface"}
          </button>
        </div>

        {ifError && (
          <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {(ifError as Error).message}
          </div>
        )}

        {showIfForm && (
          <InterfaceForm
            deviceId={deviceId}
            onCreated={() => {
              qc.invalidateQueries({ queryKey: ["wg-interfaces", deviceId] });
              setShowIfForm(false);
            }}
          />
        )}

        <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr className="text-left">
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-4 py-2.5 font-medium">Listen port</th>
                <th className="px-4 py-2.5 font-medium">Server pubkey</th>
                <th className="px-4 py-2.5 font-medium">MTU</th>
                <th className="px-4 py-2.5 font-medium text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {ifLoading && (
                <tr>
                  <td colSpan={5} className="px-4 py-5 text-center text-muted-foreground">
                    Loading…
                  </td>
                </tr>
              )}
              {!ifLoading && (!interfaces || interfaces.length === 0) && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                    No WireGuard interfaces yet.
                  </td>
                </tr>
              )}
              {interfaces?.map((i) => (
                <tr key={i.id ?? i.name} className="hover:bg-accent/30">
                  <td className="px-4 py-2.5 font-medium">{i.name}</td>
                  <td className="px-4 py-2.5 font-mono text-xs">{i.listen_port ?? "—"}</td>
                  <td className="px-4 py-2.5 break-all font-mono text-[10px]">
                    {i.public_key ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-xs">{i.mtu ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => {
                        if (
                          i.id &&
                          confirm(`Delete interface "${i.name}"? Existing peers will be orphaned.`)
                        ) {
                          delIf.mutate(i.id);
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

      {/* ---------------- Peers ---------------- */}
      <section>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold">Peers</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Per-client peers. Each peer can have a preshared key (auto-generated if you skip it) for extra security.
            </p>
          </div>
          <button
            onClick={() => setShowPeerForm((s) => !s)}
            disabled={!interfaces || interfaces.length === 0}
            title={
              !interfaces || interfaces.length === 0
                ? "Create a WG interface first"
                : ""
            }
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {showPeerForm ? "Cancel" : "+ New peer"}
          </button>
        </div>

        {showPeerForm && interfaces && interfaces.length > 0 && (
          <PeerForm
            deviceId={deviceId}
            interfaces={interfaces}
            onCreated={(id, psk) => {
              qc.invalidateQueries({ queryKey: ["wg-peers", deviceId] });
              if (psk) setCreatedPeerPsk({ id, psk });
              setShowPeerForm(false);
            }}
          />
        )}

        <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr className="text-left">
                <th className="px-4 py-2.5 font-medium">Interface</th>
                <th className="px-4 py-2.5 font-medium">Peer pubkey</th>
                <th className="px-4 py-2.5 font-medium">Allowed address</th>
                <th className="px-4 py-2.5 font-medium">Comment</th>
                <th className="px-4 py-2.5 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {peersLoading && (
                <tr>
                  <td colSpan={5} className="px-4 py-5 text-center text-muted-foreground">
                    Loading…
                  </td>
                </tr>
              )}
              {!peersLoading && (!peers || peers.length === 0) && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                    No peers yet.
                  </td>
                </tr>
              )}
              {peers?.map((p) => (
                <tr key={p.id ?? p.public_key ?? p.interface} className="hover:bg-accent/30">
                  <td className="px-4 py-2.5 font-mono text-xs">{p.interface}</td>
                  <td className="px-4 py-2.5 break-all font-mono text-[10px]">
                    {p.public_key ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs">{p.allowed_address ?? "—"}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{p.comment ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => setConfigFor(p)}
                      className="text-xs text-primary hover:underline"
                      title="Generate client .conf"
                    >
                      Download config
                    </button>
                    <button
                      onClick={() => setRestrictFor(p)}
                      className="ml-3 text-xs text-primary hover:underline"
                      title="Build firewall rules that limit which LANs this peer can reach"
                    >
                      Restrict
                    </button>
                    <button
                      onClick={() => {
                        if (p.id && confirm("Delete this peer?")) {
                          delPeer.mutate(p.id);
                        }
                      }}
                      className="ml-3 text-xs text-destructive hover:underline"
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

      {createdPeerPsk && (
        <Modal title="Peer created" onClose={() => setCreatedPeerPsk(null)}>
          <p className="mt-1 text-xs text-muted-foreground">
            The preshared key was generated server-side. Copy it now — it&apos;s also stored on the device.
          </p>
          <div className="mt-3 break-all rounded-md border border-input bg-background p-3 font-mono text-xs">
            {createdPeerPsk.psk}
          </div>
          <button
            onClick={() => setCreatedPeerPsk(null)}
            className="mt-4 block w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Close
          </button>
        </Modal>
      )}

      {configFor?.id && (
        <ConfigModal
          deviceId={deviceId}
          peer={configFor}
          onClose={() => setConfigFor(null)}
        />
      )}

      {restrictFor?.id && (
        <RestrictModal
          deviceId={deviceId}
          peer={restrictFor}
          onClose={() => setRestrictFor(null)}
        />
      )}
    </div>
  );
}

// ---------------- Forms & Modals ----------------

function InterfaceForm({
  deviceId,
  onCreated,
}: {
  deviceId: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [listenPort, setListenPort] = useState<number | "">(51820);
  const [mtu, setMtu] = useState<number | "">(1420);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createWgInterface(deviceId, {
        name,
        listen_port: typeof listenPort === "number" ? listenPort : null,
        mtu: typeof mtu === "number" ? mtu : null,
        comment: comment || null,
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <form
      onSubmit={(e) => {
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
      <div className="grid gap-4 md:grid-cols-3">
        <Field label="Name" htmlFor="if-name">
          <input
            id="if-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="wg-clients"
          />
        </Field>
        <Field label="Listen port" htmlFor="if-port">
          <input
            id="if-port"
            type="number"
            min={1}
            max={65535}
            value={listenPort}
            onChange={(e) => setListenPort(e.target.value === "" ? "" : Number(e.target.value))}
            className={input}
          />
        </Field>
        <Field label="MTU" htmlFor="if-mtu">
          <input
            id="if-mtu"
            type="number"
            min={576}
            max={9000}
            value={mtu}
            onChange={(e) => setMtu(e.target.value === "" ? "" : Number(e.target.value))}
            className={input}
          />
        </Field>
        <Field label="Comment" htmlFor="if-comment">
          <input
            id="if-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={input}
          />
        </Field>
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create interface"}
        </button>
      </div>
    </form>
  );
}

function PeerForm({
  deviceId,
  interfaces,
  onCreated,
}: {
  deviceId: string;
  interfaces: WgInterface[];
  onCreated: (id: string, psk: string | null) => void;
}) {
  const [ifaceName, setIfaceName] = useState(interfaces[0]?.name ?? "");
  const [publicKey, setPublicKey] = useState("");
  const [allowedAddress, setAllowedAddress] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createWgPeer(deviceId, {
        interface: ifaceName,
        public_key: publicKey,
        allowed_address: allowedAddress || null,
        comment: comment || null,
        // PSK omitted — server generates
      }),
    onSuccess: (res) => onCreated(res.id, res.preshared_key),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <form
      onSubmit={(e) => {
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
        <Field label="Interface" htmlFor="p-if">
          <select
            id="p-if"
            value={ifaceName}
            onChange={(e) => setIfaceName(e.target.value)}
            className={input}
          >
            {interfaces.map((i) => (
              <option key={i.name} value={i.name}>
                {i.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Allowed address" htmlFor="p-allow" hint="client's WG IP, e.g. 10.10.10.5/32">
          <input
            id="p-allow"
            value={allowedAddress}
            onChange={(e) => setAllowedAddress(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.10.10.5/32"
          />
        </Field>
        <Field
          label="Peer public key"
          htmlFor="p-pub"
          hint="generate on the client (wg genkey | wg pubkey)"
        >
          <input
            id="p-pub"
            required
            value={publicKey}
            onChange={(e) => setPublicKey(e.target.value.trim())}
            className={`${input} font-mono`}
            placeholder="base64-encoded 32-byte key"
          />
        </Field>
        <Field label="Comment" htmlFor="p-cm">
          <input
            id="p-cm"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={input}
          />
          <p className="text-[11px] italic text-muted-foreground">
            Optional · who or what this peer belongs to (e.g. nika-laptop)
          </p>
        </Field>
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending || !publicKey}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Add peer"}
        </button>
      </div>
    </form>
  );
}

function ConfigModal({
  deviceId,
  peer,
  onClose,
}: {
  deviceId: string;
  peer: WgPeer;
  onClose: () => void;
}) {
  const [endpoint, setEndpoint] = useState("");
  const [port, setPort] = useState(51820);
  const [clientAddr, setClientAddr] = useState(peer.allowed_address ?? "");
  const [dns, setDns] = useState("1.1.1.1");
  const [subnetPicks, setSubnetPicks] = useState<Set<string>>(
    () => new Set(["0.0.0.0/0", "::/0"]),
  );
  const [extraCidrs, setExtraCidrs] = useState("");
  const [keepalive, setKeepalive] = useState(25);

  const { data: endpointSuggestions } = useQuery<WgEndpointSuggestion[]>({
    queryKey: ["wg-endpoint-suggestions", deviceId],
    queryFn: () => listWgEndpointSuggestions(deviceId),
  });
  const { data: lanSubnets } = useQuery<WgSubnetSuggestion[]>({
    queryKey: ["wg-lan-subnets", deviceId],
    queryFn: () => listWgLanSubnets(deviceId),
  });

  const allowedIps = useMemo(() => {
    const fromExtra = extraCidrs
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    return [...Array.from(subnetPicks), ...fromExtra].join(", ");
  }, [subnetPicks, extraCidrs]);

  function toggleSubnet(cidr: string, on: boolean) {
    setSubnetPicks((prev) => {
      const next = new Set(prev);
      if (on) next.add(cidr);
      else next.delete(cidr);
      return next;
    });
  }

  const [confText, setConfText] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      downloadWgClientConfig(deviceId, peer.id!, {
        server_endpoint: endpoint,
        server_endpoint_port: port,
        client_address: clientAddr,
        client_dns: dns || null,
        allowed_ips: allowedIps,
        persistent_keepalive: keepalive,
      }),
    onSuccess: (res) => {
      setConfText(res.text);
      setFilename(res.filename);
    },
    onError: (e: Error) => setError(e.message),
  });

  function triggerDownload() {
    if (!confText || !filename) return;
    const blob = new Blob([confText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <Modal title="Generate WireGuard client config" onClose={onClose}>
      <p className="mt-1 text-xs text-muted-foreground">
        NetFleet doesn&apos;t store peer private keys, so this config leaves{" "}
        <span className="font-mono">PrivateKey</span> blank for the client to
        paste in their own key. To get a ready-to-use config with the key
        baked in, create the peer through the WireGuard wizard with key
        generation on. Showing this file records a reveal in the audit log.
      </p>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {confText ? (
        <div className="mt-4 space-y-3">
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            The <span className="font-mono">PrivateKey</span> line is blank —
            paste the client&apos;s own private key into it before use. NetFleet
            never stores peer private keys.
          </div>
          <pre className="max-h-72 overflow-auto rounded-md border border-input bg-background p-3 font-mono text-xs">
            {confText}
          </pre>
          <div className="flex justify-end gap-2">
            <button
              onClick={onClose}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              Close
            </button>
            <button
              onClick={triggerDownload}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Download .conf
            </button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (!endpoint) {
              setError("Server endpoint is required.");
              return;
            }
            if (!clientAddr) {
              setError("Client address is required.");
              return;
            }
            m.mutate();
          }}
          className="mt-4 space-y-3"
        >
          <Field label="Server endpoint" htmlFor="c-ep" hint="public DNS or IP of the router">
            <input
              id="c-ep"
              required
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
              className={input}
              placeholder="vpn.example.com"
              list="c-ep-suggestions"
            />
            {endpointSuggestions && endpointSuggestions.length > 0 && (
              <>
                <datalist id="c-ep-suggestions">
                  {endpointSuggestions.map((s) => (
                    <option key={`${s.address}:${s.interface}`} value={s.address}>
                      {s.interface}
                    </option>
                  ))}
                </datalist>
                <div className="mt-1 flex flex-wrap gap-1">
                  {endpointSuggestions.map((s) => (
                    <button
                      key={`${s.address}:${s.interface}`}
                      type="button"
                      onClick={() => setEndpoint(s.address)}
                      className={`rounded-md border px-2 py-0.5 text-[11px] font-mono transition hover:bg-accent ${
                        endpoint === s.address
                          ? "border-primary bg-primary/5 text-primary"
                          : "border-input bg-background text-muted-foreground"
                      }`}
                      title={`Interface: ${s.interface}`}
                    >
                      {s.address}{" "}
                      <span className="text-muted-foreground">· {s.interface}</span>
                    </button>
                  ))}
                </div>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  WAN IPs detected on this router (from /interface/list list=WAN). Type
                  a custom value to override.
                </p>
              </>
            )}
          </Field>
          <Field label="Server port" htmlFor="c-port">
            <input
              id="c-port"
              type="number"
              min={1}
              max={65535}
              required
              value={port}
              onChange={(e) => setPort(Number(e.target.value))}
              className={input}
            />
          </Field>
          <Field label="Client address" htmlFor="c-addr" hint="match peer's allowed-address">
            <input
              id="c-addr"
              required
              value={clientAddr}
              onChange={(e) => setClientAddr(e.target.value)}
              className={`${input} font-mono`}
              placeholder="10.10.10.5/24"
            />
          </Field>
          <Field label="DNS" htmlFor="c-dns">
            <input
              id="c-dns"
              value={dns}
              onChange={(e) => setDns(e.target.value)}
              className={`${input} font-mono`}
              placeholder="1.1.1.1"
            />
          </Field>
          <div className="space-y-1.5">
            <div className="text-sm font-medium">
              Allowed IPs{" "}
              <span className="text-xs font-normal text-muted-foreground">
                split tunnel · pick which traffic flows through the VPN
              </span>
            </div>
            <div className="space-y-1">
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={subnetPicks.has("0.0.0.0/0")}
                  onChange={(e) => toggleSubnet("0.0.0.0/0", e.target.checked)}
                  className="size-4"
                />
                <span className="font-mono">0.0.0.0/0</span>
                <span className="text-muted-foreground">
                  · everything (full tunnel)
                </span>
              </label>
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={subnetPicks.has("::/0")}
                  onChange={(e) => toggleSubnet("::/0", e.target.checked)}
                  className="size-4"
                />
                <span className="font-mono">::/0</span>
                <span className="text-muted-foreground">· all IPv6</span>
              </label>
              {lanSubnets?.map((s) => (
                <label
                  key={s.cidr}
                  className="flex items-center gap-2 text-xs"
                  title={
                    s.comment
                      ? `${s.interface} · ${s.comment}`
                      : `interface ${s.interface}`
                  }
                >
                  <input
                    type="checkbox"
                    checked={subnetPicks.has(s.cidr)}
                    onChange={(e) => toggleSubnet(s.cidr, e.target.checked)}
                    className="size-4"
                  />
                  <span className="font-mono">{s.cidr}</span>
                  <span className="text-muted-foreground">· {s.interface}</span>
                </label>
              ))}
              {lanSubnets && lanSubnets.length === 0 && (
                <p className="text-[11px] italic text-muted-foreground">
                  No LAN subnets discovered on this device.
                </p>
              )}
            </div>
            <label className="block text-[11px]">
              Extra CIDRs (comma or space separated)
              <input
                value={extraCidrs}
                onChange={(e) => setExtraCidrs(e.target.value)}
                className={`${input} mt-1 font-mono`}
                placeholder="172.16.0.0/12"
              />
            </label>
            <p className="text-[11px] italic text-muted-foreground">
              Final value → <span className="font-mono">{allowedIps || "—"}</span>
            </p>
          </div>
          <Field label="Keepalive" htmlFor="c-ka">
            <input
              id="c-ka"
              type="number"
              min={0}
              max={65535}
              value={keepalive}
              onChange={(e) => setKeepalive(Number(e.target.value))}
              className={input}
            />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
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
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {m.isPending ? "Generating…" : "Generate"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function RestrictModal({
  deviceId,
  peer,
  onClose,
}: {
  deviceId: string;
  peer: WgPeer;
  onClose: () => void;
}) {
  const { data: lanSubnets } = useQuery<WgSubnetSuggestion[]>({
    queryKey: ["wg-lan-subnets", deviceId],
    queryFn: () => listWgLanSubnets(deviceId),
  });
  const [picks, setPicks] = useState<Set<string>>(new Set());
  const [extra, setExtra] = useState("");
  const [dropRest, setDropRest] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createdCount, setCreatedCount] = useState<number | null>(null);

  const tag = useMemo(() => {
    // Stable identifier that survives renames — peer.id ("*4" etc.) is
    // the RouterOS-internal handle; falls back to the public key when
    // the router hasn't yet returned one.
    return peer.id?.replace(/[^a-zA-Z0-9-]/g, "") || (peer.public_key ?? "").slice(0, 8);
  }, [peer]);

  function toggle(cidr: string, on: boolean) {
    setPicks((prev) => {
      const next = new Set(prev);
      if (on) next.add(cidr);
      else next.delete(cidr);
      return next;
    });
  }

  const m = useMutation({
    mutationFn: () => {
      const extras = extra
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const allowed = [...Array.from(picks), ...extras];
      return restrictWgPeer(deviceId, peer.id!, {
        allowed_cidrs: allowed,
        drop_rest: dropRest,
        comment_tag: tag,
      });
    },
    onSuccess: (res) => {
      setCreatedCount(res.rules_created);
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Modal title="Restrict peer access" onClose={onClose}>
      <p className="mt-1 text-xs text-muted-foreground">
        Build /ip/firewall/filter rules that allow this peer only to the
        ticked destinations and drop everything else. Source matches the
        peer&apos;s allowed-address ({peer.allowed_address ?? "—"}). All rules
        carry the comment{" "}
        <span className="font-mono">netfleet wg-peer={tag}</span> so you can
        find and revoke them later.
      </p>

      {error && (
        <p className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}

      {createdCount !== null ? (
        <div className="mt-4 space-y-3">
          <p className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
            Created {createdCount} firewall rule{createdCount === 1 ? "" : "s"}.
            They live in /ip/firewall/filter; the Firewall page shows them.
          </p>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Close
            </button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (picks.size === 0 && !extra.trim() && !dropRest) {
              setError("Pick at least one allowed destination or enable drop-rest.");
              return;
            }
            m.mutate();
          }}
          className="mt-4 space-y-3"
        >
          <div className="text-sm font-medium">Allowed destinations</div>
          <div className="space-y-1 text-xs">
            {lanSubnets?.length === 0 && (
              <p className="italic text-muted-foreground">
                No LAN subnets discovered.
              </p>
            )}
            {lanSubnets?.map((s) => (
              <label
                key={s.cidr}
                className="flex items-center gap-2"
                title={s.comment ? `${s.interface} · ${s.comment}` : s.interface}
              >
                <input
                  type="checkbox"
                  checked={picks.has(s.cidr)}
                  onChange={(e) => toggle(s.cidr, e.target.checked)}
                  className="size-4"
                />
                <span className="font-mono">{s.cidr}</span>
                <span className="text-muted-foreground">· {s.interface}</span>
              </label>
            ))}
          </div>
          <label className="block text-xs">
            Extra CIDRs (comma or space separated)
            <input
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
              className={`${input} mt-1 font-mono`}
              placeholder="172.16.5.10/32"
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={dropRest}
              onChange={(e) => setDropRest(e.target.checked)}
              className="size-4"
            />
            Drop everything else from this peer
          </label>
          <div className="flex justify-end gap-2 pt-2">
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
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {m.isPending ? "Creating rules…" : "Create restrict rules"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-lg">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
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
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
