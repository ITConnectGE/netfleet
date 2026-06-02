import { api, readErrorMessage } from "@/lib/api";

export interface NicStats {
  name: string;
  ipv4: string | null;
  is_up: boolean;
  speed_mbps: number;
  rx_bytes: number;
  tx_bytes: number;
  rx_packets: number;
  tx_packets: number;
  errors_in: number;
  errors_out: number;
}

export interface PeerConnection {
  remote: string;
  count: number;
  by_state: Record<string, number>;
}

export interface HostHealth {
  sampled_at: string;
  cpu_percent: number;
  cpu_count: number;
  memory_used_bytes: number;
  memory_total_bytes: number;
  memory_percent: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  disk_percent: number;
  net_rx_bytes: number;
  net_tx_bytes: number;
  boot_at_unix: number;
  nics: NicStats[];
  peers: PeerConnection[];
}

export interface HistoryPoint {
  sampled_at: string;
  cpu_percent: number;
  memory_used_bytes: number;
  memory_total_bytes: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  net_rx_bytes: number;
  net_tx_bytes: number;
}

export interface HostHistory {
  points: HistoryPoint[];
  capacity: { rows: number; approx_bytes: number; cap_bytes: number };
}

export async function fetchHostHealth(): Promise<HostHealth> {
  try {
    return await api.get("system/host-health").json<HostHealth>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function fetchHostHistory(points = 240): Promise<HostHistory> {
  try {
    return await api
      .get(`system/host-history?points=${points}`)
      .json<HostHistory>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = Math.abs(n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}

export function formatBytesPerSec(bytesPerSec: number): string {
  if (!Number.isFinite(bytesPerSec) || bytesPerSec < 0) return "—";
  return `${formatBytes(bytesPerSec)}/s`;
}
