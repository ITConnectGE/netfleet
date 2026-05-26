"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { checkDeviceFirmware, getDeviceFirmware, type FirmwareStatus } from "@/lib/firmware";

export function FirmwareCard({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<FirmwareStatus>({
    queryKey: ["firmware", deviceId],
    queryFn: () => getDeviceFirmware(deviceId),
  });
  const recheck = useMutation({
    mutationFn: () => checkDeviceFirmware(deviceId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["firmware", deviceId] }),
  });

  if (isLoading || !data) return null;

  const upgrade = data.needs_upgrade;
  const rbUpgrade =
    data.routerboard_available &&
    data.routerboard_current &&
    data.routerboard_available !== data.routerboard_current;

  return (
    <div
      className={`rounded-lg border p-5 ${
        upgrade ? "border-amber-300 bg-amber-50/40" : "border-border bg-card"
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
          {upgrade ? (
            <span className="rounded-md bg-amber-200 px-2 py-1 text-xs font-medium text-amber-900">
              update available
            </span>
          ) : (
            <span className="rounded-md bg-emerald-100 px-2 py-1 text-xs font-medium text-emerald-800">
              up to date
            </span>
          )}
          <button
            onClick={() => recheck.mutate()}
            disabled={recheck.isPending}
            className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent disabled:opacity-50"
          >
            {recheck.isPending ? "Checking…" : "Check now"}
          </button>
        </div>
      </div>
      {recheck.error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {(recheck.error as Error).message}
        </div>
      )}
    </div>
  );
}
