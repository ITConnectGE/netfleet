import { api, readErrorMessage } from "@/lib/api";

export interface IpService {
  name: string;
  port: number;
  enabled: boolean;
  address: string | null;
  certificate: string | null;
  tls_only: boolean | null;
}

export interface IpServiceUpdate {
  enabled?: boolean;
  port?: number;
  address?: string | null;
}

export async function listIpServices(deviceId: string): Promise<IpService[]> {
  try {
    return await api.get(`devices/${deviceId}/ip-services`).json<IpService[]>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateIpService(
  deviceId: string,
  name: string,
  payload: IpServiceUpdate,
): Promise<void> {
  try {
    await api.patch(`devices/${deviceId}/ip-services/${name}`, { json: payload });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export interface DeviceUser {
  id: string | null;
  name: string;
  group: string | null;
  disabled: boolean;
  comment: string | null;
  last_logged_in: string | null;
}

export async function listDeviceUsers(deviceId: string): Promise<DeviceUser[]> {
  try {
    return await api.get(`devices/${deviceId}/system-users`).json<DeviceUser[]>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function resetDeviceUserPassword(
  deviceId: string,
  username: string,
  newPassword: string,
): Promise<void> {
  try {
    await api.post(`devices/${deviceId}/system-users/${username}/password`, {
      json: { new_password: newPassword },
    });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function setDeviceUserDisabled(
  deviceId: string,
  username: string,
  disabled: boolean,
): Promise<void> {
  try {
    await api.post(`devices/${deviceId}/system-users/${username}/disabled`, {
      json: { disabled },
    });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
