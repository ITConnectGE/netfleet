"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  checkDeviceFirmware,
  getAutoUpgradePolicy,
  getDeviceFirmware,
  getFirmwareUpgradeStatus,
  setAutoUpgradePolicy,
  triggerFirmwareUpgrade,
  type AutoUpgradePolicy,
  type FirmwareStatus,
  type FirmwareUpgradeStatus,
} from "@/lib/firmware";

export function FirmwareCard({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<FirmwareStatus>({
    queryKey: ["firmware", deviceId],
    queryFn: () => getDeviceFirmware(deviceId),
  });
  const { data: upgradeStatus } = useQuery<FirmwareUpgradeStatus>({
    queryKey: ["firmware-upgrade-status", deviceId],
    queryFn: () => getFirmwareUpgradeStatus(deviceId),
  });
  const { data: policy } = useQuery<AutoUpgradePolicy>({
    queryKey: ["firmware-policy", deviceId],
    queryFn: () => getAutoUpgradePolicy(deviceId),
  });

  const recheck = useMutation({
    mutationFn: () => checkDeviceFirmware(deviceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["firmware", deviceId] });
      qc.invalidateQueries({ queryKey: ["firmware-upgrade-status", deviceId] });
    },
  });
  const upgrade = useMutation({
    mutationFn: (opts: { include_routerboard: boolean }) =>
      triggerFirmwareUpgrade(deviceId, opts),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["firmware", deviceId] });
      qc.invalidateQueries({ queryKey: ["firmware-upgrade-status", deviceId] });
    },
  });

  if (isLoading || !data) return null;

  const needsUpgrade = data.needs_upgrade;
  const rbUpgrade =
    data.routerboard_available &&
    data.routerboard_current &&
    data.routerboard_available !== data.routerboard_current;

  return (
    <div
      className={`rounded-lg border p-5 ${
        needsUpgrade ? "border-amber-300 bg-amber-50/40" : "border-border bg-card"
      }`}
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-medium text-muted-foreground">Firmware</h3>
          <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <span className="text-muted-foreground">RouterOS</span>
            <span className="font-mono">
              {data.current_version ?? "—"}
              {data.available_version && data.available_version !== data.current_version && (
                <>
                  {" "}→{" "}
                  <span className="font-semibold text-amber-900">
                    {data.available_version}
                  </span>
                </>
              )}
            </span>
            {data.routerboard_current && (
              <>
                <span className="text-muted-foreground">RouterBOARD</span>
                <span className="font-mono">
                  {data.routerboard_current}
                  {rbUpgrade && (
                    <>
                      {" "}→{" "}
                      <span className="font-semibold text-amber-900">
                        {data.routerboard_available}
                      </span>
                    </>
                  )}
                </span>
              </>
            )}
            <span className="text-muted-foreground">Channel</span>
            <span className="font-mono text-xs">{data.channel ?? "—"}</span>
            <span className="text-muted-foreground">Last checked</span>
            <span className="text-xs text-muted-foreground">
              {data.checked_at ? new Date(data.checked_at).toLocaleString() : "never"}
            </span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          {needsUpgrade ? (
            <span className="rounded-md bg-amber-200 px-2 py-1 text-xs font-medium text-amber-900">
              update available
            </span>
          ) : (
            <span className="rounded-md bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-800">
              up to date
            </span>
          )}
          <div className="flex gap-1.5">
            <button
              onClick={() => recheck.mutate()}
              disabled={recheck.isPending}
              className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent disabled:opacity-50"
            >
              {recheck.isPending ? "Checking…" : "Check now"}
            </button>
            {needsUpgrade && (
              <button
                onClick={() => {
                  const rbAvailable = Boolean(rbUpgrade);
                  const includeRb =
                    rbAvailable &&
                    confirm(
                      "Also upgrade RouterBOARD bootloader? (adds a second reboot)",
                    );
                  if (
                    confirm(
                      `Trigger RouterOS upgrade ${data.current_version ?? "?"} → ${data.available_version}?\n\nThe device will reboot.`,
                    )
                  ) {
                    upgrade.mutate({ include_routerboard: includeRb });
                  }
                }}
                disabled={upgrade.isPending}
                className="rounded-md border border-amber-400 bg-amber-100 px-2 py-1 text-xs font-medium text-amber-900 hover:bg-amber-200 disabled:opacity-50"
              >
                {upgrade.isPending ? "Upgrading…" : "Upgrade now"}
              </button>
            )}
          </div>
        </div>
      </div>

      {upgrade.data && (
        <div className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
          {upgrade.data.message}
        </div>
      )}
      {recheck.error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {(recheck.error as Error).message}
        </div>
      )}
      {upgrade.error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {(upgrade.error as Error).message}
        </div>
      )}

      {upgradeStatus?.last_status && (
        <div className="mt-4 rounded-md border border-border bg-background/60 px-3 py-2 text-xs">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-muted-foreground">Last upgrade</span>
            <UpgradeStatusPill status={upgradeStatus.last_status} />
          </div>
          <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
            <span>Triggered</span>
            <span>
              {upgradeStatus.last_triggered_at
                ? new Date(upgradeStatus.last_triggered_at).toLocaleString()
                : "—"}
            </span>
            <span>From → To</span>
            <span className="font-mono">
              {upgradeStatus.last_from_version ?? "?"} →{" "}
              {upgradeStatus.last_to_version ?? "?"}
            </span>
            {upgradeStatus.last_error && (
              <>
                <span>Error</span>
                <span className="break-all font-mono text-destructive">
                  {upgradeStatus.last_error}
                </span>
              </>
            )}
          </div>
        </div>
      )}

      <PolicyForm deviceId={deviceId} initial={policy} />
    </div>
  );
}

function UpgradeStatusPill({ status }: { status: "pending" | "succeeded" | "failed" }) {
  const cls =
    status === "succeeded"
      ? "bg-emerald-100 text-emerald-800"
      : status === "pending"
        ? "bg-amber-100 text-amber-900"
        : "bg-red-100 text-red-800";
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {status}
    </span>
  );
}

function PolicyForm({
  deviceId,
  initial,
}: {
  deviceId: string;
  initial: AutoUpgradePolicy | undefined;
}) {
  const qc = useQueryClient();
  const [enabled, setEnabled] = useState(false);
  const [start, setStart] = useState<string>("");
  const [end, setEnd] = useState<string>("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (!initial || dirty) return;
    setEnabled(initial.enabled);
    setStart(initial.window_start_hour?.toString() ?? "");
    setEnd(initial.window_end_hour?.toString() ?? "");
  }, [initial, dirty]);

  const save = useMutation({
    mutationFn: () =>
      setAutoUpgradePolicy(deviceId, {
        enabled,
        window_start_hour: start === "" ? null : Number(start),
        window_end_hour: end === "" ? null : Number(end),
      }),
    onSuccess: () => {
      setDirty(false);
      qc.invalidateQueries({ queryKey: ["firmware-policy", deviceId] });
    },
  });

  const markDirty = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setDirty(true);
  };

  return (
    <details className="mt-4 rounded-md border border-border bg-background/40 px-3 py-2 text-xs">
      <summary className="cursor-pointer text-muted-foreground">
        Auto-upgrade policy{" "}
        {initial?.enabled && (
          <span className="ml-2 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">
            on
          </span>
        )}
      </summary>
      <div className="mt-3 space-y-2">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => markDirty(setEnabled)(e.target.checked)}
          />
          <span>Apply RouterOS upgrades automatically when an update is detected</span>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-muted-foreground">Window start (UTC hour)</span>
            <input
              type="number"
              min={0}
              max={23}
              value={start}
              onChange={(e) => markDirty(setStart)(e.target.value)}
              placeholder="any"
              className="mt-0.5 block w-full rounded-md border border-input bg-background px-2 py-1 font-mono"
            />
          </label>
          <label className="block">
            <span className="text-muted-foreground">Window end (UTC hour)</span>
            <input
              type="number"
              min={0}
              max={23}
              value={end}
              onChange={(e) => markDirty(setEnd)(e.target.value)}
              placeholder="any"
              className="mt-0.5 block w-full rounded-md border border-input bg-background px-2 py-1 font-mono"
            />
          </label>
        </div>
        <p className="text-[10px] text-muted-foreground">
          Leave both blank to allow upgrades at any time. The window is inclusive
          of start, exclusive of end, and may wrap midnight.
        </p>
        <button
          onClick={() => save.mutate()}
          disabled={!dirty || save.isPending}
          className="rounded-md border border-input bg-background px-3 py-1 text-xs font-medium hover:bg-accent disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save policy"}
        </button>
        {save.error && (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-[11px] text-destructive">
            {(save.error as Error).message}
          </div>
        )}
      </div>
    </details>
  );
}
