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
  /** Unix hosts only. RouterOS leaves these at their defaults. */
  uid?: number | null;
  gid?: number | null;
  groups?: string[];
  shell?: string | null;
  home?: string | null;
  is_system?: boolean;
  /** root, and the account NetFleet manages the host with. The server
   *  refuses to modify these; the UI disables the controls so the refusal
   *  is visible before the click rather than after. */
  is_protected?: boolean;
}

export interface DeviceGroup {
  name: string;
  gid: number | null;
  members: string[];
  is_system: boolean;
}

export interface DeviceUserCreate {
  username: string;
  password?: string | null;
  groups?: string[];
  shell?: string | null;
  comment?: string | null;
  create_home?: boolean;
}

export async function listDeviceGroups(deviceId: string): Promise<DeviceGroup[]> {
  return api.get(`devices/${deviceId}/system-groups`).json<DeviceGroup[]>();
}

export async function createDeviceUser(
  deviceId: string,
  payload: DeviceUserCreate,
): Promise<void> {
  try {
    await api.post(`devices/${deviceId}/system-users`, { json: payload });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteDeviceUser(
  deviceId: string,
  username: string,
  removeHome = false,
): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/system-users/${username}`, {
      searchParams: { remove_home: String(removeHome) },
    });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function setDeviceUserGroups(
  deviceId: string,
  username: string,
  groups: string[],
): Promise<void> {
  try {
    await api.put(`devices/${deviceId}/system-users/${username}/groups`, {
      json: { groups },
    });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function createDeviceGroup(
  deviceId: string,
  name: string,
): Promise<void> {
  try {
    await api.post(`devices/${deviceId}/system-groups`, { json: { name } });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteDeviceGroup(
  deviceId: string,
  name: string,
): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/system-groups/${name}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
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
