import { api, readErrorMessage } from "@/lib/api";

// ---------------- Pools ----------------

export interface DhcpPool {
  id: string | null;
  name: string;
  ranges: string;
  next_pool: string | null;
  comment: string | null;
}

export interface DhcpPoolCreate {
  name: string;
  ranges: string;
  next_pool?: string | null;
  comment?: string | null;
}

export type DhcpPoolUpdate = Partial<DhcpPoolCreate>;

export async function listDhcpPools(deviceId: string): Promise<DhcpPool[]> {
  return api.get(`devices/${deviceId}/dhcp/pools`).json<DhcpPool[]>();
}

export async function createDhcpPool(
  deviceId: string,
  payload: DhcpPoolCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/dhcp/pools`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateDhcpPool(
  deviceId: string,
  poolId: string,
  payload: DhcpPoolUpdate,
): Promise<void> {
  try {
    await api.patch(`devices/${deviceId}/dhcp/pools/${encodeURIComponent(poolId)}`, {
      json: payload,
    });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteDhcpPool(deviceId: string, poolId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/dhcp/pools/${encodeURIComponent(poolId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Servers ----------------

export interface DhcpServer {
  id: string | null;
  name: string;
  interface: string;
  address_pool: string | null;
  lease_time: string | null;
  authoritative: string | null;
  disabled: boolean;
  comment: string | null;
}

export interface DhcpServerCreate {
  name: string;
  interface: string;
  address_pool?: string | null;
  lease_time?: string | null;
  authoritative?: string | null;
  disabled?: boolean;
  comment?: string | null;
}

export type DhcpServerUpdate = Partial<DhcpServerCreate>;

export async function listDhcpServers(deviceId: string): Promise<DhcpServer[]> {
  return api.get(`devices/${deviceId}/dhcp/servers`).json<DhcpServer[]>();
}

export async function createDhcpServer(
  deviceId: string,
  payload: DhcpServerCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/dhcp/servers`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateDhcpServer(
  deviceId: string,
  serverId: string,
  payload: DhcpServerUpdate,
): Promise<void> {
  try {
    await api.patch(
      `devices/${deviceId}/dhcp/servers/${encodeURIComponent(serverId)}`,
      { json: payload },
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteDhcpServer(deviceId: string, serverId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/dhcp/servers/${encodeURIComponent(serverId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Networks ----------------

export interface DhcpNetwork {
  id: string | null;
  address: string;
  gateway: string | null;
  netmask: string | null;
  dns_servers: string | null;
  ntp_servers: string | null;
  domain: string | null;
  comment: string | null;
}

export interface DhcpNetworkCreate {
  address: string;
  gateway?: string | null;
  netmask?: string | null;
  dns_servers?: string | null;
  ntp_servers?: string | null;
  domain?: string | null;
  comment?: string | null;
}

export type DhcpNetworkUpdate = Partial<DhcpNetworkCreate>;

export async function listDhcpNetworks(deviceId: string): Promise<DhcpNetwork[]> {
  return api.get(`devices/${deviceId}/dhcp/networks`).json<DhcpNetwork[]>();
}

export async function createDhcpNetwork(
  deviceId: string,
  payload: DhcpNetworkCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/dhcp/networks`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateDhcpNetwork(
  deviceId: string,
  networkId: string,
  payload: DhcpNetworkUpdate,
): Promise<void> {
  try {
    await api.patch(
      `devices/${deviceId}/dhcp/networks/${encodeURIComponent(networkId)}`,
      { json: payload },
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteDhcpNetwork(
  deviceId: string,
  networkId: string,
): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/dhcp/networks/${encodeURIComponent(networkId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Leases ----------------

export interface DhcpLease {
  id: string | null;
  address: string;
  mac_address: string;
  host_name: string | null;
  client_id: string | null;
  status: string | null;
  server: string | null;
  expires_at_iso: string | null;
  dynamic: boolean;
  blocked: boolean;
  comment: string | null;
}

export async function listDhcpLeases(deviceId: string): Promise<DhcpLease[]> {
  return api.get(`devices/${deviceId}/dhcp/leases`).json<DhcpLease[]>();
}

export async function makeLeaseStatic(
  deviceId: string,
  leaseId: string,
): Promise<void> {
  try {
    await api.post(
      `devices/${deviceId}/dhcp/leases/${encodeURIComponent(leaseId)}/make-static`,
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function setLeaseComment(
  deviceId: string,
  leaseId: string,
  comment: string | null,
): Promise<void> {
  try {
    await api.patch(
      `devices/${deviceId}/dhcp/leases/${encodeURIComponent(leaseId)}/comment`,
      { json: { comment } },
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteLease(
  deviceId: string,
  leaseId: string,
): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/dhcp/leases/${encodeURIComponent(leaseId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
