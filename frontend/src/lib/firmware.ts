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

export interface FirmwareUpgradeStatus {
  last_triggered_at: string | null;
  last_status: "pending" | "succeeded" | "failed" | null;
  last_error: string | null;
  last_from_version: string | null;
  last_to_version: string | null;
}

export interface FirmwareUpgradeResult {
  triggered: boolean;
  will_reboot: boolean;
  from_version: string | null;
  to_version: string | null;
  message: string;
}

export interface AutoUpgradePolicy {
  enabled: boolean;
  window_start_hour: number | null;
  window_end_hour: number | null;
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

export type FirmwareUpgradeTarget = "routeros" | "routerboard" | "both";

export async function triggerFirmwareUpgrade(
  deviceId: string,
  opts: { target: FirmwareUpgradeTarget },
): Promise<FirmwareUpgradeResult> {
  try {
    return await api
      .post(`devices/${deviceId}/firmware/upgrade`, {
        json: { target: opts.target },
        timeout: 60_000,
      })
      .json<FirmwareUpgradeResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function getFirmwareUpgradeStatus(
  deviceId: string,
): Promise<FirmwareUpgradeStatus> {
  return api
    .get(`devices/${deviceId}/firmware/upgrade-status`)
    .json<FirmwareUpgradeStatus>();
}

export async function getAutoUpgradePolicy(deviceId: string): Promise<AutoUpgradePolicy> {
  return api.get(`devices/${deviceId}/firmware/policy`).json<AutoUpgradePolicy>();
}

export async function setAutoUpgradePolicy(
  deviceId: string,
  policy: AutoUpgradePolicy,
): Promise<AutoUpgradePolicy> {
  try {
    return await api
      .put(`devices/${deviceId}/firmware/policy`, { json: policy })
      .json<AutoUpgradePolicy>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
