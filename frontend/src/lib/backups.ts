import { api, readErrorMessage } from "@/lib/api";

import { authStorage } from "@/lib/auth-storage";

export interface DeviceBackup {
  id: string;
  ts: string;
  device_id: string;
  triggered_by_user_id: string | null;
  source: "scheduled" | "manual";
  status: "ok" | "failed";
  backup_filename: string | null;
  rsc_filename: string | null;
  backup_size_bytes: number | null;
  rsc_size_bytes: number | null;
  error_message: string | null;
  duration_ms: number | null;
}

export async function listDeviceBackups(
  deviceId: string,
  limit = 50,
): Promise<DeviceBackup[]> {
  return api
    .get(`devices/${deviceId}/backups`, { searchParams: { limit } })
    .json<DeviceBackup[]>();
}

export async function triggerBackup(deviceId: string): Promise<DeviceBackup> {
  try {
    return await api
      .post(`devices/${deviceId}/backups`, { timeout: 120_000 })
      .json<DeviceBackup>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

/** Open a download in a new tab using the current bearer token. */
export function backupDownloadUrl(
  deviceId: string,
  backupId: string,
  kind: "backup" | "rsc",
): string {
  return `/api/v1/devices/${deviceId}/backups/${backupId}/file/${kind}`;
}

/** Streamed download — pulls the file and pushes a Save-As dialog. */
export async function downloadBackupFile(
  deviceId: string,
  backupId: string,
  kind: "backup" | "rsc",
  filename: string,
): Promise<void> {
  const token = authStorage.getAccessToken();
  const res = await fetch(backupDownloadUrl(deviceId, backupId, kind), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`download failed: HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export interface RestoreResult {
  ok: boolean;
  filename: string;
  device_will_reboot: boolean;
}

/** Upload .backup to the device via SFTP and trigger /system/backup/load.
 *  RouterOS reboots immediately on success — surfacing as a connection drop. */
export async function restoreBackup(
  deviceId: string,
  backupId: string,
): Promise<RestoreResult> {
  try {
    return await api
      .post(`devices/${deviceId}/backups/${backupId}/restore`, { timeout: 60_000 })
      .json<RestoreResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
