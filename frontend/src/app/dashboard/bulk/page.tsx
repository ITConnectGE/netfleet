"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import {
  bulkAddressListAdd,
  bulkFirewallFilterAdd,
  bulkResetDeviceUserPassword,
  type BulkAddressListAddResponse,
  type BulkFirewallFilterResponse,
  type BulkPasswordResetResponse,
  type BulkResult,
} from "@/lib/bulk";
import { listDevices, type Device } from "@/lib/devices";
import { listSites, type Site } from "@/lib/sites";

type Tab = "password" | "address-list" | "firewall";

const TABS: { id: Tab; label: string; description: string }[] = [
  {
    id: "password",
    label: "Password reset",
    description: "Reset a device-local user across many devices in parallel.",
  },
  {
    id: "address-list",
    label: "Address list",
    description: "Append an IP / CIDR to a named firewall address-list.",
  },
  {
    id: "firewall",
    label: "Firewall rule",
    description: "Add the same /ip/firewall/filter rule to many devices.",
  },
];

export default function BulkPage() {
  const [tab, setTab] = useState<Tab>("password");
  const current = TABS.find((t) => t.id === tab)!;
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Bulk operations</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Run an action across many devices at once. Each device is contacted in
        parallel and reported individually.
      </p>

      <div className="mt-6 inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded px-3 py-1.5 font-medium transition ${
              tab === t.id
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{current.description}</p>

      <div className="mt-6">
        {tab === "password" && <BulkPasswordResetCard />}
        {tab === "address-list" && <BulkAddressListCard />}
        {tab === "firewall" && <BulkFirewallFilterCard />}
      </div>
    </div>
  );
}

// ---------------- Shared device picker ----------------

interface DevicePickerProps {
  selected: Set<string>;
  setSelected: (next: Set<string>) => void;
}

function useDevicePicker() {
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: () => listSites(),
  });
  const siteIndex = useMemo(
    () => Object.fromEntries((sites ?? []).map((s) => [s.id, s.name])),
    [sites],
  );
  return { devices, sites, siteIndex };
}

function DevicePicker({
  selected,
  setSelected,
}: DevicePickerProps) {
  const { devices, sites, siteIndex } = useDevicePicker();
  const [siteFilter, setSiteFilter] = useState("");

  const filteredDevices = useMemo(() => {
    if (!devices) return [];
    if (!siteFilter) return devices;
    return devices.filter((d) => d.site_id === siteFilter);
  }, [devices, siteFilter]);

  const allSelected =
    filteredDevices.length > 0 &&
    filteredDevices.every((d) => selected.has(d.id));

  function toggleAll() {
    const next = new Set(selected);
    if (allSelected) {
      filteredDevices.forEach((d) => next.delete(d.id));
    } else {
      filteredDevices.forEach((d) => next.add(d.id));
    }
    setSelected(next);
  }

  function toggleOne(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="space-y-1 text-xs font-medium text-muted-foreground">
          Filter by site
          <select
            value={siteFilter}
            onChange={(e) => setSiteFilter(e.target.value)}
            className={`${input} mt-1`}
          >
            <option value="">All sites</option>
            {sites?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-muted-foreground">
          {selected.size} of {filteredDevices.length} selected
        </span>
      </div>
      <div className="mt-3 overflow-hidden rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="w-10 px-3 py-2">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="size-4 rounded"
                />
              </th>
              <th className="px-3 py-2 font-medium">Device</th>
              <th className="px-3 py-2 font-medium">Site</th>
              <th className="px-3 py-2 font-medium">Host</th>
              <th className="px-3 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredDevices.map((d) => (
              <tr key={d.id} className="hover:bg-accent/30">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={selected.has(d.id)}
                    onChange={() => toggleOne(d.id)}
                    className="size-4 rounded"
                  />
                </td>
                <td className="px-3 py-2 font-medium">{d.name}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  {siteIndex[d.site_id] ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{d.host}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {d.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------- Result table ----------------

function ResultPanel({
  total,
  succeeded,
  failed,
  skipped,
  results,
}: {
  total: number;
  succeeded: number;
  failed: number;
  skipped: number;
  results: BulkResult[];
}) {
  return (
    <div className="mt-8">
      <h3 className="text-sm font-medium">Result</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        {succeeded} succeeded · {failed} failed · {skipped} skipped of {total}
      </p>
      <div className="mt-3 overflow-hidden rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">Device</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {results.map((r) => (
              <tr key={r.device_id}>
                <td className="px-3 py-2">{r.device_name ?? r.device_id}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-md px-1.5 py-0.5 text-xs ${
                      r.status === "ok"
                        ? "bg-emerald-100 text-emerald-800"
                        : r.status === "skipped"
                          ? "bg-zinc-100 text-zinc-800"
                          : "bg-red-100 text-red-800"
                    }`}
                  >
                    {r.status}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                  {r.error ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------- Tab 1: Password reset ----------------

function BulkPasswordResetCard() {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation<BulkPasswordResetResponse>({
    mutationFn: () =>
      bulkResetDeviceUserPassword(Array.from(selected), username, password),
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (selected.size === 0) return setError("Select at least one device.");
    if (!username) return setError("Username is required.");
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirm) return setError("Passwords do not match.");
    m.mutate();
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <form onSubmit={onSubmit} className="space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Device username</span>
            <input
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={input}
              placeholder="admin"
              autoComplete="off"
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">New password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={input}
              autoComplete="new-password"
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Confirm</span>
            <input
              type="password"
              required
              minLength={8}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className={input}
              autoComplete="new-password"
            />
          </label>
        </div>

        <DevicePicker selected={selected} setSelected={setSelected} />

        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={m.isPending || selected.size === 0}
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending
              ? `Resetting ${selected.size} devices…`
              : `Reset password on ${selected.size} device${selected.size === 1 ? "" : "s"}`}
          </button>
        </div>
      </form>

      {m.data && <ResultPanel {...m.data} />}
    </div>
  );
}

// ---------------- Tab 2: Address list ----------------

function BulkAddressListCard() {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [listName, setListName] = useState("");
  const [address, setAddress] = useState("");
  const [timeout, setTimeoutVal] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation<BulkAddressListAddResponse>({
    mutationFn: () =>
      bulkAddressListAdd({
        device_ids: Array.from(selected),
        list_name: listName,
        address,
        timeout: timeout || null,
        comment: comment || null,
      }),
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (selected.size === 0) return setError("Select at least one device.");
    if (!listName) return setError("List name is required.");
    if (!address) return setError("Address is required.");
    m.mutate();
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <form onSubmit={onSubmit} className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1.5">
            <span className="text-sm font-medium">List name</span>
            <input
              required
              value={listName}
              onChange={(e) => setListName(e.target.value)}
              className={input}
              placeholder="blacklist"
            />
            <p className="text-[11px] italic text-muted-foreground">
              The /ip/firewall/address-list group to append to. Created on
              demand by RouterOS.
            </p>
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Address</span>
            <input
              required
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className={`${input} font-mono`}
              placeholder="203.0.113.10 or 10.0.0.0/24"
            />
            <p className="text-[11px] italic text-muted-foreground">
              IP, CIDR or hostname (resolved on the router).
            </p>
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Timeout</span>
            <input
              value={timeout}
              onChange={(e) => setTimeoutVal(e.target.value)}
              className={input}
              placeholder="1d, 12h, 30m"
            />
            <p className="text-[11px] italic text-muted-foreground">
              Optional · auto-remove after this duration. Empty = permanent.
            </p>
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Comment</span>
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className={input}
              placeholder="ticket-12345"
            />
          </label>
        </div>

        <DevicePicker selected={selected} setSelected={setSelected} />

        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={m.isPending || selected.size === 0}
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending
              ? `Updating ${selected.size} devices…`
              : `Add to address-list on ${selected.size} device${selected.size === 1 ? "" : "s"}`}
          </button>
        </div>
      </form>

      {m.data && <ResultPanel {...m.data} />}
    </div>
  );
}

// ---------------- Tab 3: Firewall rule ----------------

function BulkFirewallFilterCard() {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [chain, setChain] = useState("forward");
  const [action, setAction] = useState("drop");
  const [srcAddress, setSrcAddress] = useState("");
  const [dstAddress, setDstAddress] = useState("");
  const [srcAddressList, setSrcAddressList] = useState("");
  const [dstAddressList, setDstAddressList] = useState("");
  const [protocol, setProtocol] = useState("");
  const [srcPort, setSrcPort] = useState("");
  const [dstPort, setDstPort] = useState("");
  const [connectionState, setConnectionState] = useState("");
  const [log, setLog] = useState(false);
  const [logPrefix, setLogPrefix] = useState("");
  const [disabled, setDisabled] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation<BulkFirewallFilterResponse>({
    mutationFn: () =>
      bulkFirewallFilterAdd({
        device_ids: Array.from(selected),
        rule: {
          chain,
          action,
          src_address: srcAddress || null,
          dst_address: dstAddress || null,
          src_address_list: srcAddressList || null,
          dst_address_list: dstAddressList || null,
          protocol: protocol || null,
          src_port: srcPort || null,
          dst_port: dstPort || null,
          connection_state: connectionState || null,
          log,
          log_prefix: logPrefix || null,
          disabled,
          comment: comment || null,
        },
      }),
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (selected.size === 0) return setError("Select at least one device.");
    if (!chain) return setError("Chain is required.");
    if (!action) return setError("Action is required.");
    m.mutate();
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <form onSubmit={onSubmit} className="space-y-6">
        <div className="grid gap-4 md:grid-cols-4">
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Chain</span>
            <select
              value={chain}
              onChange={(e) => setChain(e.target.value)}
              className={input}
            >
              <option value="input">input</option>
              <option value="forward">forward</option>
              <option value="output">output</option>
            </select>
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Action</span>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className={input}
            >
              <option value="accept">accept</option>
              <option value="drop">drop</option>
              <option value="reject">reject</option>
              <option value="log">log</option>
            </select>
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Protocol</span>
            <input
              value={protocol}
              onChange={(e) => setProtocol(e.target.value)}
              className={input}
              placeholder="tcp"
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Connection state</span>
            <input
              value={connectionState}
              onChange={(e) => setConnectionState(e.target.value)}
              className={input}
              placeholder="new,invalid"
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Src address</span>
            <input
              value={srcAddress}
              onChange={(e) => setSrcAddress(e.target.value)}
              className={`${input} font-mono`}
              placeholder="192.0.2.0/24"
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Dst address</span>
            <input
              value={dstAddress}
              onChange={(e) => setDstAddress(e.target.value)}
              className={`${input} font-mono`}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Src address-list</span>
            <input
              value={srcAddressList}
              onChange={(e) => setSrcAddressList(e.target.value)}
              className={input}
              placeholder="blacklist"
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Dst address-list</span>
            <input
              value={dstAddressList}
              onChange={(e) => setDstAddressList(e.target.value)}
              className={input}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Src port</span>
            <input
              value={srcPort}
              onChange={(e) => setSrcPort(e.target.value)}
              className={input}
              placeholder="22"
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Dst port</span>
            <input
              value={dstPort}
              onChange={(e) => setDstPort(e.target.value)}
              className={input}
              placeholder="80,443"
            />
          </label>
          <label className="space-y-1.5 md:col-span-2">
            <span className="text-sm font-medium">Comment</span>
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className={input}
              placeholder="bulk-block: ticket-123"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-6 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={log}
              onChange={(e) => setLog(e.target.checked)}
              className="size-4 rounded"
            />
            Log hits
          </label>
          {log && (
            <input
              value={logPrefix}
              onChange={(e) => setLogPrefix(e.target.value)}
              className={`${input} max-w-xs font-mono`}
              placeholder="BULK-DROP"
            />
          )}
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={disabled}
              onChange={(e) => setDisabled(e.target.checked)}
              className="size-4 rounded"
            />
            Create as disabled
          </label>
        </div>

        <DevicePicker selected={selected} setSelected={setSelected} />

        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={m.isPending || selected.size === 0}
            className="rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending
              ? `Adding rule on ${selected.size} devices…`
              : `Add firewall rule on ${selected.size} device${selected.size === 1 ? "" : "s"}`}
          </button>
        </div>
      </form>

      {m.data && <ResultPanel {...m.data} />}
    </div>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
