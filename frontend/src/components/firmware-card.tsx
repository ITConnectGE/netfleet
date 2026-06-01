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

/**
 * Compact firmware widget for the device overview. Designed to sit on
 * a single row most of the time and fold the auto-upgrade policy / last
 * upgrade detail behind <details> so the overview doesn't get a
 * card-on-card wall. RouterBOARD bootloader status is intentionally not
 * shown here — operators that need it can read /system/routerboard on
 * the device or check the Firmware service page.
 */
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
    mutationFn: () => triggerFirmwareUpgrade(deviceId, { target: "routeros" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["firmware", deviceId] });
      qc.invalidateQueries({ queryKey: ["firmware-upgrade-status", deviceId] });
    },
  });

  if (isLoading || !data) return null;
  const fw = data;
  const needsUpgrade = fw.needs_upgrade;

  function confirmUpgrade(): boolean {
    return confirm(
      `Install RouterOS ${fw.available_version} (currently ${fw.current_version ?? "?"})?\n\n` +
        "The device will reboot — 3–5 min downtime, active sessions interrupted.\n" +
        "Recommended: take a Backup first.",
    );
  }

  return (
    <div
      className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border px-3 py-2 text-sm ${
        needsUpgrade ? "border-amber-300 bg-amber-50/40" : "border-border bg-card"
      }`}
    >
      <span className="font-medium text-muted-foreground">Firmware</span>

      {needsUpgrade ? (
        <span className="rounded-md bg-amber-200 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
          update available
        </span>
      ) : (
        <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">
          up to date
        </span>
      )}

      <span className="font-mono">
        {fw.current_version ?? "—"}
        {needsUpgrade && (
          <>
            <span className="mx-1 text-muted-foreground">→</span>
            <span className="font-semibold text-amber-900">
              {fw.available_version ?? "—"}
            </span>
          </>
        )}
      </span>

      <span className="text-xs text-muted-foreground">
        ch <span className="font-mono">{fw.channel ?? "—"}</span>
      </span>
      <span className="text-xs text-muted-foreground">
        checked{" "}
        {fw.checked_at
          ? new Date(fw.checked_at).toLocaleString(undefined, {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })
          : "never"}
      </span>

      <div className="ml-auto flex items-center gap-2">
        {needsUpgrade && (
          <button
            onClick={() => {
              if (confirmUpgrade()) upgrade.mutate();
            }}
            disabled={upgrade.isPending}
            className="rounded-md border border-amber-400 bg-amber-100 px-2 py-1 text-xs font-medium text-amber-900 hover:bg-amber-200 disabled:opacity-50"
          >
            {upgrade.isPending ? "Upgrading…" : "Upgrade RouterOS"}
          </button>
        )}
        <button
          onClick={() => recheck.mutate()}
          disabled={recheck.isPending}
          className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent disabled:opacity-50"
        >
          {recheck.isPending ? "Checking…" : "Check"}
        </button>
        <FirmwareDetails
          deviceId={deviceId}
          upgradeStatus={upgradeStatus}
          policy={policy}
        />
      </div>

      {/* Inline error / success — small, doesn't blow up the row height */}
      {(upgrade.data || recheck.error || upgrade.error) && (
        <div className="w-full text-xs">
          {upgrade.data && (
            <span className="text-emerald-800">{upgrade.data.message}</span>
          )}
          {recheck.error && (
            <span className="text-destructive">
              {(recheck.error as Error).message}
            </span>
          )}
          {upgrade.error && (
            <span className="text-destructive">
              {(upgrade.error as Error).message}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function FirmwareDetails({
  deviceId,
  upgradeStatus,
  policy,
}: {
  deviceId: string;
  upgradeStatus: FirmwareUpgradeStatus | undefined;
  policy: AutoUpgradePolicy | undefined;
}) {
  const hasLastUpgrade = Boolean(upgradeStatus?.last_status);
  const hasAutoOn = Boolean(policy?.enabled);
  // Hide "Details" entirely on a clean device with no auto-upgrade
  // policy + no prior upgrades — there's literally nothing to show.
  const empty = !hasLastUpgrade && !hasAutoOn && !policy;
  if (empty) {
    return null;
  }
  return (
    <details className="relative">
      <summary className="cursor-pointer list-none rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent">
        Details{" "}
        {hasAutoOn && (
          <span className="ml-1 rounded-md bg-emerald-100 px-1 py-0.5 text-[9px] font-medium text-emerald-800">
            auto on
          </span>
        )}
      </summary>
      <div className="absolute right-0 z-30 mt-1 w-80 space-y-3 rounded-md border border-border bg-popover p-3 text-xs shadow-md">
        {hasLastUpgrade && upgradeStatus?.last_status && (
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="font-medium text-muted-foreground">
                Last upgrade
              </span>
              <UpgradeStatusPill status={upgradeStatus.last_status} />
            </div>
            <div className="grid grid-cols-[6rem_1fr] gap-y-0.5 text-[11px] text-muted-foreground">
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
    </details>
  );
}

function UpgradeStatusPill({
  status,
}: {
  status: "pending" | "succeeded" | "failed";
}) {
  const cls =
    status === "succeeded"
      ? "bg-emerald-100 text-emerald-800"
      : status === "pending"
        ? "bg-amber-100 text-amber-900"
        : "bg-red-100 text-red-800";
  return (
    <span
      className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium ${cls}`}
    >
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
    <div className="border-t border-border pt-2">
      <div className="mb-2 font-medium text-muted-foreground">
        Auto-upgrade policy
      </div>
      <label className="flex items-start gap-2 text-[11px]">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => markDirty(setEnabled)(e.target.checked)}
          className="mt-0.5"
        />
        <span>Apply RouterOS upgrades automatically</span>
      </label>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <label className="block text-[10px]">
          <span className="text-muted-foreground">Window start (UTC h)</span>
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
        <label className="block text-[10px]">
          <span className="text-muted-foreground">Window end (UTC h)</span>
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
      <p className="mt-2 text-[10px] text-muted-foreground">
        Leave both blank for any time; the window can wrap midnight.
      </p>
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={() => save.mutate()}
          disabled={!dirty || save.isPending}
          className="rounded-md border border-input bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save policy"}
        </button>
        {save.error && (
          <span className="text-[11px] text-destructive">
            {(save.error as Error).message}
          </span>
        )}
      </div>
    </div>
  );
}
