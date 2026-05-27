"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { bulkResetDeviceUserPassword, type BulkPasswordResetResponse } from "@/lib/bulk";
import { listDevices, type Device } from "@/lib/devices";
import { listSites, type Site } from "@/lib/sites";

export default function BulkPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Bulk operations</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Run an action across many devices at once. Each device is contacted in parallel
        and reported individually.
      </p>

      <div className="mt-8">
        <BulkPasswordResetCard />
      </div>
    </div>
  );
}

function BulkPasswordResetCard() {
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const { data: sites } = useQuery<Site[]>({ queryKey: ["sites"], queryFn: () => listSites() });
  const siteIndex = useMemo(
    () => Object.fromEntries((sites ?? []).map((s) => [s.id, s.name])),
    [sites],
  );

  const [siteFilter, setSiteFilter] = useState<string>("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const filteredDevices = useMemo(() => {
    if (!devices) return [];
    if (!siteFilter) return devices;
    return devices.filter((d) => d.site_id === siteFilter);
  }, [devices, siteFilter]);

  const m = useMutation<BulkPasswordResetResponse>({
    mutationFn: () => bulkResetDeviceUserPassword(Array.from(selected), username, password),
    onError: (e: Error) => setError(e.message),
  });

  const allSelected = filteredDevices.length > 0 && filteredDevices.every((d) => selected.has(d.id));

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        filteredDevices.forEach((d) => next.delete(d.id));
      } else {
        filteredDevices.forEach((d) => next.add(d.id));
      }
      return next;
    });
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (selected.size === 0) {
      setError("Select at least one device.");
      return;
    }
    if (!username) {
      setError("Username is required.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    m.mutate();
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <h2 className="text-lg font-semibold">Bulk password reset</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Reset the password for a given <strong>device user</strong> (e.g. <code>admin</code>)
        across selected devices.
      </p>

      <form onSubmit={onSubmit} className="mt-6 space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Filter by site</span>
            <select
              value={siteFilter}
              onChange={(e) => setSiteFilter(e.target.value)}
              className={inputClass}
            >
              <option value="">All sites</option>
              {sites?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Device username</span>
            <input
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={inputClass}
              placeholder="admin"
              autoComplete="off"
            />
          </label>
          <div className="space-y-1.5">
            <span className="text-sm font-medium">Selected</span>
            <div className="rounded-md border border-input bg-background px-3 py-2 text-sm text-muted-foreground">
              {selected.size} of {filteredDevices.length}
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1.5">
            <span className="text-sm font-medium">New password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
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
              className={inputClass}
              autoComplete="new-password"
            />
          </label>
        </div>

        <div className="overflow-hidden rounded-md border border-border">
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
                  <td className="px-3 py-2 text-xs text-muted-foreground">{d.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
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

      {m.data && (
        <div className="mt-8">
          <h3 className="text-sm font-medium">Result</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {m.data.succeeded} succeeded · {m.data.failed} failed · {m.data.skipped} skipped
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
                {m.data.results.map((r) => (
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
      )}
    </div>
  );
}

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
