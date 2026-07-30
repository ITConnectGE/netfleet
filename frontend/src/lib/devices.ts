import { api, readErrorMessage } from "@/lib/api";

export type DeviceStatus = "unknown" | "online" | "offline" | "error";
export type DeviceTransport = "api" | "rest" | "ssh" | "netconf";
export type DeviceClass = "network" | "server";
export type BecomeMethod = "none" | "sudo";

/** Vendors whose devices are servers rather than network gear. Mirrors
 *  SERVER_VENDORS in the backend's device schema. */
export const SERVER_VENDORS = new Set(["linux"]);

export interface Device {
  id: string;
  organization_id: string;
  site_id: string;
  vendor: string;
  device_class: DeviceClass;
  name: string;
  host: string;
  port: number;
  ssh_port: number;
  transport: DeviceTransport;
  verify_tls: boolean;
  username: string;
  has_password: boolean;
  has_api_key: boolean;
  has_ssh_key: boolean;
  become_method: BecomeMethod;
  ssh_host_key_fingerprint: string | null;
  model: string | null;
  serial: string | null;
  firmware: string | null;
  os_family: string | null;
  os_version: string | null;
  firmware_available: string | null;
  firmware_checked_at: string | null;
  routerboard_current: string | null;
  routerboard_available: string | null;
  status: DeviceStatus;
  status_error: string | null;
  last_seen_at: string | null;
  is_enabled: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeviceCreate {
  site_id: string;
  vendor: string;
  name: string;
  host: string;
  port?: number;
  ssh_port?: number;
  transport?: DeviceTransport;
  verify_tls?: boolean;
  username: string;
  password?: string | null;
  api_key?: string | null;
  /** SSH vendors only: have NetFleet generate the keypair. The public half
   *  is handed to the onboarding script; the private half never leaves the DB. */
  generate_ssh_key?: boolean;
  ssh_private_key?: string | null;
  become_method?: BecomeMethod;
  become_password?: string | null;
  notes?: string | null;
}

export interface DeviceUpdate {
  name?: string;
  host?: string;
  port?: number;
  ssh_port?: number;
  transport?: DeviceTransport;
  verify_tls?: boolean;
  username?: string;
  password?: string | null;
  api_key?: string | null;
  ssh_private_key?: string | null;
  become_method?: BecomeMethod;
  become_password?: string | null;
  /** Clears the pinned host key so the next connection re-pins it. */
  reset_host_key?: boolean;
  site_id?: string;
  is_enabled?: boolean;
  notes?: string | null;
}

export interface TestConnectionResult {
  ok: boolean;
  status: "online" | "offline" | "error";
  error: string | null;
  identity: string | null;
  model: string | null;
  firmware: string | null;
  uptime_seconds: number | null;
}

export async function listDevices(siteId?: string): Promise<Device[]> {
  const searchParams = siteId ? { site_id: siteId } : undefined;
  return api.get("devices", { searchParams }).json<Device[]>();
}

export async function getDevice(id: string): Promise<Device> {
  return api.get(`devices/${id}`).json<Device>();
}

export async function createDevice(payload: DeviceCreate): Promise<Device> {
  try {
    return await api.post("devices", { json: payload }).json<Device>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateDevice(id: string, payload: DeviceUpdate): Promise<Device> {
  try {
    return await api.patch(`devices/${id}`, { json: payload }).json<Device>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteDevice(id: string): Promise<void> {
  try {
    await api.delete(`devices/${id}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function testDeviceConnection(id: string): Promise<TestConnectionResult> {
  return api.post(`devices/${id}/test-connection`).json<TestConnectionResult>();
}

export async function rebootDevice(id: string): Promise<void> {
  try {
    await api.post(`devices/${id}/reboot`, { timeout: 30_000 });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function getOnboardingScript(
  id: string,
  options: { includePassword?: boolean } = {},
): Promise<string> {
  const includePassword = options.includePassword ?? true;
  try {
    return await api
      .get(`devices/${id}/onboarding-script`, {
        searchParams: { include_password: String(includePassword) },
      })
      .text();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
