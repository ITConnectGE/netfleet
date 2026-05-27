"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

import {
  downloadBackupFile,
  listDeviceBackups,
  restoreBackup,
  triggerBackup,
  type DeviceBackup,
} from "@/lib/backups";
import { formatBytes } from "@/lib/network";

export default function BackupsPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const qc = useQueryClient();

  const { data: rows, isLoading, error } = useQuery<DeviceBackup[]>({
    queryKey: ["backups", deviceId],
    queryFn: () => listDeviceBackups(deviceId),
  });

  const run = useMutation({
    mutationFn: () => triggerBackup(deviceId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups", deviceId] }),
  });

  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [restoreOk, setRestoreOk] = useState<string | null>(null);
  const restore = useMutation({
    mutationFn: (backupId: string) => restoreBackup(deviceId, backupId),
    onMutate: (backupId) => {
      setRestoringId(backupId);
      setRestoreError(null);
      setRestoreOk(null);
    },
    onSuccess: (r) => {
      setRestoreOk(`Restore dispatched (${r.filename}). The device is rebooting now.`);
      setRestoringId(null);
    },
    onError: (e: Error) => {
      setRestoreError(e.message);
      setRestoringId(null);
    },
  });

  function onRestore(b: DeviceBackup) {
    if (!b.backup_filename) return;
    const ok = confirm(
      `Restore "${b.backup_filename}" to this device?\n\n` +
        `• The device will REBOOT immediately after the backup is applied.\n` +
        `• Active sessions and traffic will be interrupted.\n` +
        `• This action cannot be undone from the UI — only by restoring an older backup.\n\n` +
        `Continue?`,
    );
    if (!ok) return;
    restore.mutate(b.id);
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Device backups</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Nightly automatic backups + on-demand. The binary <code>.backup</code> is what
            RouterOS restores from; the <code>.rsc</code> is the human-readable export script.
          </p>
        </div>
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {run.isPending ? "Backing up…" : "Backup now"}
        </button>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}
      {run.error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(run.error as Error).message}
        </div>
      )}
      {restoreError && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Restore failed: {restoreError}
        </div>
      )}
      {restoreOk && (
        <div className="mt-4 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          {restoreOk}
        </div>
      )}

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2.5 font-medium">When</th>
              <th className="px-3 py-2.5 font-medium">Source</th>
              <th className="px-3 py-2.5 font-medium">Status</th>
              <th className="px-3 py-2.5 font-medium">Backup file</th>
              <th className="px-3 py-2.5 font-medium">RSC file</th>
              <th className="px-3 py-2.5 font-medium text-right">Duration</th>
              <th className="px-3 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (!rows || rows.length === 0) && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                  No backups yet. Click <strong>Backup now</strong> or wait for the nightly job.
                </td>
              </tr>
            )}
            {rows?.map((b) => (
              <tr key={b.id} className="hover:bg-accent/30">
                <td className="px-3 py-2 font-mono text-xs">
                  {new Date(b.ts).toLocaleString()}
                </td>
                <td className="px-3 py-2 text-xs">
                  <span
                    className={`rounded-md px-1.5 py-0.5 text-[10px] ${
                      b.source === "manual"
                        ? "bg-sky-100 text-sky-900"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {b.source}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs">
                  {b.status === "ok" ? (
                    <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-emerald-800">
                      ok
                    </span>
                  ) : (
                    <span
                      className="rounded-md bg-red-100 px-1.5 py-0.5 text-red-800"
                      title={b.error_message ?? ""}
                    >
                      failed
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 font-mono text-[11px]">
                  {b.backup_filename ? (
                    <div className="flex items-baseline gap-2">
                      <span>{b.backup_filename}</span>
                      <span className="text-[10px] text-muted-foreground">
                        ({formatBytes(b.backup_size_bytes)})
                      </span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-3 py-2 font-mono text-[11px]">
                  {b.rsc_filename ? (
                    <div className="flex items-baseline gap-2">
                      <span>{b.rsc_filename}</span>
                      <span className="text-[10px] text-muted-foreground">
                        ({formatBytes(b.rsc_size_bytes)})
                      </span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs text-muted-foreground">
                  {b.duration_ms !== null ? `${(b.duration_ms / 1000).toFixed(1)}s` : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  {b.backup_filename && (
                    <button
                      onClick={() =>
                        downloadBackupFile(deviceId, b.id, "backup", b.backup_filename!)
                      }
                      className="text-xs text-primary hover:underline"
                    >
                      .backup
                    </button>
                  )}
                  {b.rsc_filename && (
                    <button
                      onClick={() => downloadBackupFile(deviceId, b.id, "rsc", b.rsc_filename!)}
                      className="ml-3 text-xs text-primary hover:underline"
                    >
                      .rsc
                    </button>
                  )}
                  {b.backup_filename && b.status === "ok" && (
                    <button
                      onClick={() => onRestore(b)}
                      disabled={restoringId !== null}
                      className="ml-3 text-xs font-medium text-destructive hover:underline disabled:opacity-50"
                      title="Upload this .backup to the device and run /system/backup/load (device will reboot)"
                    >
                      {restoringId === b.id ? "Restoring…" : "Restore"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
