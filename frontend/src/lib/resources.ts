import { api } from "@/lib/api";

/**
 * Live resource snapshot, read from the device on request.
 *
 * Every field is optional: RouterOS reports percentages, a Linux host also
 * reports absolute figures, and a field the platform cannot answer is
 * absent rather than zero.
 */
export interface SystemResources {
  identity: string;
  model: string | null;
  serial: string | null;
  firmware: string | null;
  os_family: string | null;
  os_version: string | null;
  uptime_seconds: number | null;
  cpu_count: number | null;
  cpu_load_pct: number | null;
  load_avg_1: number | null;
  load_avg_5: number | null;
  load_avg_15: number | null;
  memory_used_pct: number | null;
  memory_total_bytes: number | null;
  memory_used_bytes: number | null;
  swap_total_bytes: number | null;
  swap_used_bytes: number | null;
}

export interface DiskUsage {
  filesystem: string;
  mount_point: string;
  fs_type: string | null;
  total_bytes: number | null;
  used_bytes: number | null;
  available_bytes: number | null;
  used_pct: number | null;
  inodes_total: number | null;
  inodes_used: number | null;
  inodes_used_pct: number | null;
}

export async function getResources(deviceId: string): Promise<SystemResources> {
  return api
    .get(`devices/${deviceId}/resources`, { timeout: 30_000 })
    .json<SystemResources>();
}

export async function getDisks(deviceId: string): Promise<DiskUsage[]> {
  return api.get(`devices/${deviceId}/disks`, { timeout: 30_000 }).json<DiskUsage[]>();
}

/** Binary units, because that is what `df` and `/proc/meminfo` report. */
export function formatBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  // Sub-10 values keep a decimal so "1.4 GiB" does not collapse to "1 GiB".
  return `${v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

export function formatUptime(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
