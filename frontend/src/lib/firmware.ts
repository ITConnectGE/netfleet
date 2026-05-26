import { api, readErrorMessage } from "@/lib/api";

export interface FirmwareStatus {
  current_version: string | null;
  available_version: string | null;
  channel: string | null;
  checked_at: string | null;
  routerboard_current: string | null;
  routerboard_available: string | null;
  needs_upgrade: boolean;
}

export interface FleetFirmwareSummary {
  total: number;
  updates_available: number;
  checked_ever: number;
  never_checked: number;
}

export async function getFleetFirmwareSummary(): Promise<FleetFirmwareSummary> {
  return api.get("firmware/summary").json<FleetFirmwareSummary>();
}

export async function getDeviceFirmware(deviceId: string): Promise<FirmwareStatus> {
  return api.get(`devices/${deviceId}/firmware`).json<FirmwareStatus>();
}

export async function checkDeviceFirmware(deviceId: string): Promise<FirmwareStatus> {
  try {
    return await api
      .post(`devices/${deviceId}/firmware/check`, { timeout: 60_000 })
      .json<FirmwareStatus>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
