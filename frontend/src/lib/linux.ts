import { api } from "@/lib/api";

/** One interface's addressing, denormalised — see InterfaceConfig on the API. */
export interface InterfaceConfig {
  name: string;
  mac_address: string | null;
  state: string | null;
  admin_up: boolean | null;
  mtu: number | null;
  type: string | null;
  vlan_id: number | null;
  vlan_parent: string | null;
  /** "dhcp" | "static" | "unmanaged" | "unknown" */
  method: string | null;
  addresses: string[];
  netmask: string | null;
  gateway: string | null;
  dns_servers: string[];
  dns_search: string[];
  dhcp_server: string | null;
  lease_expires_iso: string | null;
  rx_bytes: number | null;
  tx_bytes: number | null;
  /** systemd-networkd / NetworkManager. Null means nothing claims it. */
  managed_by: string | null;
}

export interface DirEntryUsage {
  path: string;
  name: string;
  size_bytes: number;
  is_dir: boolean;
}

export interface ProcessInfo {
  pid: number;
  user: string | null;
  cpu_pct: number | null;
  mem_pct: number | null;
  rss_bytes: number | null;
  state: string | null;
  started: string | null;
  cpu_time: string | null;
  command: string;
  threads: number | null;
}

export async function getInterfaceConfigs(
  deviceId: string,
): Promise<InterfaceConfig[]> {
  return api
    .get(`devices/${deviceId}/interface-configs`, { timeout: 40_000 })
    .json<InterfaceConfig[]>();
}

export async function getDiskTree(
  deviceId: string,
  path: string,
): Promise<DirEntryUsage[]> {
  return api
    .get(`devices/${deviceId}/disk-tree`, {
      searchParams: { path },
      // du on a large tree is genuinely slow, and this is user-initiated.
      timeout: 130_000,
    })
    .json<DirEntryUsage[]>();
}

export async function getProcesses(
  deviceId: string,
  limit = 40,
): Promise<ProcessInfo[]> {
  return api
    .get(`devices/${deviceId}/processes`, {
      searchParams: { limit: String(limit) },
      timeout: 40_000,
    })
    .json<ProcessInfo[]>();
}

export async function syncNtpNow(deviceId: string): Promise<{ message: string }> {
  return api
    .post(`devices/${deviceId}/ntp/sync`, { timeout: 40_000 })
    .json<{ message: string }>();
}

/** Human label for the addressing method, including the null case. */
export function methodLabel(method: string | null): string {
  switch (method) {
    case "dhcp":
      return "DHCP";
    case "static":
      return "Static";
    case "unmanaged":
      return "No address";
    default:
      return "Unknown";
  }
}
