"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import { listDevices, type Device } from "@/lib/devices";
import { checkDeviceFirmware, triggerFirmwareUpgrade } from "@/lib/firmware";
import { normFw, runPool } from "@/lib/pool";
import { listSites, type Site } from "@/lib/sites";

// Upgrades reboot routers. Keep the blast radius of one click modest: a
// handful at a time, so a bad release shows up on the first few results
// rather than on the whole fleet simultaneously.
const UPGRADE_CONCURRENCY = 4;
const CHECK_CONCURRENCY = 6;

type ResultKind = "running" | "triggered" | "skipped" | "failed";
interface DeviceResult {
  kind: ResultKind;
  message?: string;
}

/** Devices that share a model and an exact current → available pair. */
interface Group {
  key: string;
  model: string;
  from: string;
  to: string;
  devices: Device[];
}

function groupKey(model: string, from: string, to: string) {
  return `${model}\u0000${from}\u0000${to}`;
}

function upgradable(d: Device): boolean {
  return (
    d.is_enabled &&
    d.device_class !== "server" &&
    Boolean(d.firmware) &&
    Boolean(d.firmware_available) &&
    normFw(d.firmware) !== normFw(d.firmware_available)
  );
}

export default function BulkFirmwarePage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: () => listSites(),
  });
  const siteName = useMemo(
    () => Object.fromEntries((sites ?? []).map((s) => [s.id, s.name])),
    [sites],
  );

  const groups = useMemo<Group[]>(() => {
    const map = new Map<string, Group>();
    for (const d of devices ?? []) {
      if (!upgradable(d)) continue;
      const model = d.model ?? "Unknown model";
      const from = normFw(d.firmware);
      const to = normFw(d.firmware_available);
      const key = groupKey(model, from, to);
      const g = map.get(key) ?? { key, model, from, to, devices: [] };
      g.devices.push(d);
      map.set(key, g);
    }
    for (const g of map.values()) g.devices.sort((a, b) => a.name.localeCompare(b.name));
    return [...map.values()].sort(
      (a, b) => a.model.localeCompare(b.model) || a.from.localeCompare(b.from),
    );
  }, [devices]);

  const networkCount = useMemo(
    () => (devices ?? []).filter((d) => d.is_enabled && d.device_class !== "server").length,
    [devices],
  );
  const neverChecked = useMemo(
    () =>
      (devices ?? []).filter(
        (d) => d.is_enabled && d.device_class !== "server" && !d.firmware_checked_at,
      ).length,
    [devices],
  );

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [checking, setChecking] = useState<{ done: number; total: number } | null>(null);
  const [results, setResults] = useState<Map<string, DeviceResult>>(new Map());
  const [running, setRunning] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Drop selections whose device left every group (upgraded, or a re-check
  // moved it to a different version).
  const selectable = useMemo(
    () => new Set(groups.flatMap((g) => g.devices.map((d) => d.id))),
    [groups],
  );
  const effective = useMemo(
    () => new Set([...selected].filter((id) => selectable.has(id))),
    [selected, selectable],
  );

  function toggleGroup(g: Group) {
    const next = new Set(selected);
    const all = g.devices.every((d) => next.has(d.id));
    for (const d of g.devices) {
      if (all) next.delete(d.id);
      else next.add(d.id);
    }
    setSelected(next);
    setConfirming(false);
  }

  function toggleDevice(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
    setConfirming(false);
  }

  async function recheckAll() {
    const targets = (devices ?? []).filter(
      (d) => d.is_enabled && d.device_class !== "server",
    );
    if (targets.length === 0) return;
    let done = 0;
    let failed = 0;
    setChecking({ done, total: targets.length });
    await runPool(targets, CHECK_CONCURRENCY, async (d) => {
      try {
        await checkDeviceFirmware(d.id);
      } catch {
        failed++;
      }
      done++;
      setChecking({ done, total: targets.length });
    });
    await queryClient.invalidateQueries({ queryKey: ["devices"] });
    setChecking(null);
    if (failed) {
      toast.warning("Firmware check finished", `${failed} device(s) could not be reached.`);
    } else {
      toast.success("Firmware check finished", `${targets.length} device(s) checked.`);
    }
  }

  async function upgradeSelected() {
    setConfirming(false);
    // Snapshot what the operator approved: the model and exact from → to
    // versions of each device's group at the moment they clicked.
    const plan: { device: Device; group: Group }[] = [];
    for (const g of groups) {
      for (const d of g.devices) {
        if (effective.has(d.id)) plan.push({ device: d, group: g });
      }
    }
    if (plan.length === 0) return;
    setRunning(true);
    const state = new Map<string, DeviceResult>(
      plan.map(({ device }) => [device.id, { kind: "running" }]),
    );
    const mark = (id: string, r: DeviceResult) => {
      state.set(id, r);
      setResults(new Map(state));
    };
    setResults(new Map(state));

    await runPool(plan, UPGRADE_CONCURRENCY, async ({ device, group }) => {
      try {
        // Re-ask the router right now. If it was upgraded by hand, or a
        // newer release appeared since the list was loaded, it no longer
        // matches what was approved — skip it rather than install a
        // version nobody looked at.
        const fresh = await checkDeviceFirmware(device.id);
        const cur = normFw(fresh.current_version);
        const avail = normFw(fresh.available_version);
        if (cur !== group.from || avail !== group.to) {
          mark(device.id, {
            kind: "skipped",
            message:
              cur === avail || !avail
                ? `already on ${cur || "?"}`
                : `now ${cur || "?"} → ${avail}, expected ${group.from} → ${group.to}`,
          });
          return;
        }
        await triggerFirmwareUpgrade(device.id, { target: "routeros" });
        mark(device.id, { kind: "triggered", message: `${group.from} → ${group.to}, rebooting` });
      } catch (e) {
        mark(device.id, { kind: "failed", message: (e as Error).message });
      }
    });

    setRunning(false);
    setSelected(new Set());
    await queryClient.invalidateQueries({ queryKey: ["devices"] });
    const vals = [...state.values()];
    const triggered = vals.filter((v) => v.kind === "triggered").length;
    const skipped = vals.filter((v) => v.kind === "skipped").length;
    const failed = vals.filter((v) => v.kind === "failed").length;
    const summary = `${triggered} upgrading, ${skipped} skipped, ${failed} failed.`;
    if (failed) toast.warning("Bulk upgrade finished", summary);
    else toast.success("Bulk upgrade finished", summary);
  }

  const resultRows = useMemo(() => {
    const byId = new Map((devices ?? []).map((d) => [d.id, d]));
    return [...results.entries()].map(([id, r]) => ({ id, r, device: byId.get(id) }));
  }, [results, devices]);

  const busy = running || checking !== null;

  return (
    <div>
      <Link href="/dashboard/bulk" className="text-xs text-muted-foreground hover:underline">
        ← Bulk operations
      </Link>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Bulk firmware upgrade</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
        Routers with a pending RouterOS update, grouped by model and exact{" "}
        <span className="font-mono">current → available</span> version. Pick whole
        groups or individual routers. Just before each upgrade the router is checked
        again, and it is skipped if its version no longer matches its group.
        Each router reboots once its upgrade starts.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={recheckAll}
          disabled={busy}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm font-medium hover:bg-accent/60 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {checking
            ? `Checking ${checking.done}/${checking.total}…`
            : "⟳ Check all for updates"}
        </button>
        <span className="text-xs text-muted-foreground">
          {networkCount} router{networkCount === 1 ? "" : "s"} ·{" "}
          {selectable.size} with an update
          {neverChecked > 0 ? ` · ${neverChecked} never checked` : ""}
        </span>
      </div>

      {devices && groups.length === 0 ? (
        <div className="mt-6 rounded-lg border-2 border-dashed border-border/60 bg-card/50 p-10 text-center">
          <p className="text-sm font-medium">Every router is on its latest available version.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Versions come from the last firmware check. Run “Check all for updates” to ask
            the routers again.
          </p>
        </div>
      ) : (
        <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-muted/80 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr className="border-b border-border">
                <th scope="col" className="w-10 px-3 py-2.5" />
                <th scope="col" className="px-3 py-2.5 font-medium">Model</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Current</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Available</th>
                <th scope="col" className="px-3 py-2.5 font-medium">Routers</th>
                <th scope="col" className="px-3 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => {
                const picked = g.devices.filter((d) => effective.has(d.id)).length;
                const open = expanded.has(g.key);
                return (
                  <GroupRows
                    key={g.key}
                    group={g}
                    picked={picked}
                    open={open}
                    disabled={busy}
                    selected={effective}
                    siteName={siteName}
                    results={results}
                    onToggleGroup={() => toggleGroup(g)}
                    onToggleDevice={toggleDevice}
                    onToggleOpen={() => {
                      const next = new Set(expanded);
                      if (open) next.delete(g.key);
                      else next.add(g.key);
                      setExpanded(next);
                    }}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {confirming ? (
          <>
            <span className="text-sm text-amber-700 dark:text-amber-400">
              {effective.size} router{effective.size === 1 ? "" : "s"} will install the update
              and reboot. Continue?
            </span>
            <button
              type="button"
              onClick={upgradeSelected}
              className="rounded-md bg-destructive px-4 py-1.5 text-sm font-medium text-destructive-foreground hover:opacity-90"
            >
              Yes, upgrade and reboot
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent/60"
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={busy || effective.size === 0}
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {running
              ? "Upgrading…"
              : `Upgrade ${effective.size} selected router${effective.size === 1 ? "" : "s"}`}
          </button>
        )}
      </div>

      {resultRows.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold">Results</h2>
          <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-card text-sm">
            {resultRows.map(({ id, r, device }) => (
              <li key={id} className="flex flex-wrap items-baseline gap-x-3 px-3 py-2">
                <ResultBadge kind={r.kind} />
                <Link href={`/dashboard/devices/${id}`} className="font-medium hover:underline">
                  {device?.name ?? id}
                </Link>
                {r.message && (
                  <span className="text-xs text-muted-foreground">{r.message}</span>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            Routers that are upgrading come back on the new version in a few minutes. Run
            “Check all for updates” afterwards to confirm. RouterBOARD bootloader upgrades
            are still done per device.
          </p>
        </div>
      )}
    </div>
  );
}

function GroupRows({
  group,
  picked,
  open,
  disabled,
  selected,
  siteName,
  results,
  onToggleGroup,
  onToggleDevice,
  onToggleOpen,
}: {
  group: Group;
  picked: number;
  open: boolean;
  disabled: boolean;
  selected: Set<string>;
  siteName: Record<string, string>;
  results: Map<string, DeviceResult>;
  onToggleGroup: () => void;
  onToggleDevice: (id: string) => void;
  onToggleOpen: () => void;
}) {
  const all = picked === group.devices.length;
  return (
    <>
      <tr className="border-t border-border">
        <td className="px-3 py-2">
          <input
            type="checkbox"
            aria-label={`Select all ${group.model} on ${group.from}`}
            checked={all}
            ref={(el) => {
              if (el) el.indeterminate = picked > 0 && !all;
            }}
            onChange={onToggleGroup}
            disabled={disabled}
          />
        </td>
        <td className="px-3 py-2 font-medium">{group.model}</td>
        <td className="px-3 py-2 font-mono text-xs">{group.from}</td>
        <td className="px-3 py-2 font-mono text-xs">
          <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-amber-900">
            ↑ {group.to}
          </span>
        </td>
        <td className="px-3 py-2 text-xs text-muted-foreground">
          {picked > 0 ? `${picked} of ${group.devices.length}` : group.devices.length}
        </td>
        <td className="px-3 py-2 text-right">
          <button
            type="button"
            onClick={onToggleOpen}
            aria-expanded={open}
            className="text-xs text-primary hover:underline"
          >
            {open ? "Hide routers" : "Show routers"}
          </button>
        </td>
      </tr>
      {open &&
        group.devices.map((d) => {
          const r = results.get(d.id);
          return (
            <tr key={d.id} className="bg-muted/20 text-xs">
              <td className="px-3 py-1.5 pl-6">
                <input
                  type="checkbox"
                  aria-label={`Select ${d.name}`}
                  checked={selected.has(d.id)}
                  onChange={() => onToggleDevice(d.id)}
                  disabled={disabled}
                />
              </td>
              <td className="px-3 py-1.5" colSpan={2}>
                <Link href={`/dashboard/devices/${d.id}`} className="font-medium hover:underline">
                  {d.name}
                </Link>
                <span className="ml-2 text-muted-foreground">{siteName[d.site_id] ?? ""}</span>
              </td>
              <td className="px-3 py-1.5 font-mono text-muted-foreground">{d.host}</td>
              <td className="px-3 py-1.5 text-muted-foreground">{d.status}</td>
              <td className="px-3 py-1.5 text-right">{r ? <ResultBadge kind={r.kind} /> : null}</td>
            </tr>
          );
        })}
    </>
  );
}

function ResultBadge({ kind }: { kind: ResultKind }) {
  const styles: Record<ResultKind, string> = {
    running: "bg-muted text-muted-foreground",
    triggered: "bg-emerald-100 text-emerald-900",
    skipped: "bg-slate-100 text-slate-700",
    failed: "bg-red-100 text-red-900",
  };
  const label: Record<ResultKind, string> = {
    running: "working…",
    triggered: "upgrading",
    skipped: "skipped",
    failed: "failed",
  };
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${styles[kind]}`}>
      {label[kind]}
    </span>
  );
}
