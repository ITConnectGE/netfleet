import { api, readErrorMessage } from "@/lib/api";

export interface NtpClient {
  enabled: boolean;
  mode: string | null;
  servers: string | null;
  primary: string | null;
  secondary: string | null;
}

export interface NtpUpdate {
  enabled?: boolean;
  mode?: "unicast" | "broadcast" | "multicast" | "manycast";
  servers?: string | null;
  primary?: string | null;
  secondary?: string | null;
}

export interface NtpServer {
  enabled: boolean;
  broadcast: boolean | null;
  multicast: boolean | null;
  manycast: boolean | null;
  auth_key: string | null;
}

export interface NtpServerUpdate {
  enabled?: boolean;
  broadcast?: boolean;
  multicast?: boolean;
  manycast?: boolean;
}

export interface DeviceClock {
  time: string | null;
  date: string | null;
  time_zone_name: string | null;
  time_zone_autodetect: boolean | null;
  gmt_offset: string | null;
  dst_active: boolean | null;
}

export interface SnmpSettings {
  enabled: boolean;
  contact: string | null;
  location: string | null;
  trap_target: string | null;
  trap_version: string | null;
  engine_id: string | null;
}

export interface SnmpUpdate {
  enabled?: boolean;
  contact?: string | null;
  location?: string | null;
  trap_target?: string | null;
  trap_version?: "1" | "2" | "3";
}

export interface SnmpCommunity {
  id: string | null;
  name: string;
  addresses: string | null;
  security: string | null;
  read_access: boolean;
  write_access: boolean;
  disabled: boolean;
}

export interface SnmpCommunityCreate {
  name: string;
  addresses?: string | null;
  security?: "none" | "authorized" | "private";
  read_access: boolean;
  write_access: boolean;
}

export interface SnmpCommunityUpdate {
  name?: string;
  addresses?: string | null;
  security?: "none" | "authorized" | "private";
  read_access?: boolean;
  write_access?: boolean;
  disabled?: boolean;
}

export async function getNtp(deviceId: string): Promise<NtpClient> {
  return api.get(`devices/${deviceId}/ntp`).json<NtpClient>();
}
export async function updateNtp(deviceId: string, payload: NtpUpdate): Promise<void> {
  try {
    await api.patch(`devices/${deviceId}/ntp`, { json: payload });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function getNtpServer(deviceId: string): Promise<NtpServer> {
  return api.get(`devices/${deviceId}/ntp-server`).json<NtpServer>();
}
export async function updateNtpServer(
  deviceId: string,
  payload: NtpServerUpdate,
): Promise<void> {
  try {
    await api.patch(`devices/${deviceId}/ntp-server`, { json: payload });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function getDeviceClock(deviceId: string): Promise<DeviceClock> {
  return api.get(`devices/${deviceId}/clock`).json<DeviceClock>();
}

export interface DeviceClockUpdate {
  time_zone_name?: string | null;
  time_zone_autodetect?: boolean | null;
}

export async function updateDeviceClock(
  deviceId: string,
  payload: DeviceClockUpdate,
): Promise<void> {
  try {
    await api.patch(`devices/${deviceId}/clock`, { json: payload });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function getSnmp(deviceId: string): Promise<SnmpSettings> {
  return api.get(`devices/${deviceId}/snmp`).json<SnmpSettings>();
}
export async function updateSnmp(deviceId: string, payload: SnmpUpdate): Promise<void> {
  try {
    await api.patch(`devices/${deviceId}/snmp`, { json: payload });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function listSnmpCommunities(deviceId: string): Promise<SnmpCommunity[]> {
  return api.get(`devices/${deviceId}/snmp/communities`).json<SnmpCommunity[]>();
}
export async function createSnmpCommunity(
  deviceId: string,
  payload: SnmpCommunityCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/snmp/communities`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
export async function deleteSnmpCommunity(deviceId: string, id: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/snmp/communities/${encodeURIComponent(id)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
export async function updateSnmpCommunity(
  deviceId: string,
  id: string,
  payload: SnmpCommunityUpdate,
): Promise<void> {
  try {
    await api.patch(`devices/${deviceId}/snmp/communities/${encodeURIComponent(id)}`, {
      json: payload,
    });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
