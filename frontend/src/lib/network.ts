import { api, readErrorMessage } from "@/lib/api";

export async function resetInterfaceCounters(
  deviceId: string,
  interfaceName: string,
): Promise<void> {
  try {
    await api.post(
      `devices/${deviceId}/interfaces/${encodeURIComponent(interfaceName)}/reset-counters`,
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Routes ----------------

export interface IpRoute {
  id: string | null;
  dst_address: string;
  gateway: string | null;
  distance: number | null;
  routing_table: string | null;
  pref_src: string | null;
  active: boolean | null;
  dynamic: boolean | null;
  static: boolean | null;
  disabled: boolean;
  comment: string | null;
}

export interface IpRouteCreate {
  dst_address: string;
  gateway?: string | null;
  distance?: number | null;
  routing_table?: string | null;
  pref_src?: string | null;
  disabled?: boolean;
  comment?: string | null;
}

export async function listRoutes(deviceId: string): Promise<IpRoute[]> {
  return api.get(`devices/${deviceId}/routes`).json<IpRoute[]>();
}
export async function createRoute(
  deviceId: string,
  payload: IpRouteCreate,
): Promise<{ id: string }> {
  try {
    return await api.post(`devices/${deviceId}/routes`, { json: payload }).json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
export async function deleteRoute(deviceId: string, routeId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/routes/${encodeURIComponent(routeId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- ARP ----------------

export interface ArpEntry {
  id: string | null;
  address: string;
  mac_address: string | null;
  interface: string | null;
  complete: boolean | null;
  dynamic: boolean | null;
  invalid: boolean | null;
  comment: string | null;
}

export async function listArp(deviceId: string): Promise<ArpEntry[]> {
  return api.get(`devices/${deviceId}/arp`).json<ArpEntry[]>();
}

// ---------------- Neighbours (CDP / LLDP / MNDP) ----------------

export interface Neighbor {
  id: string | null;
  interface: string | null;
  address: string | null;
  address6: string | null;
  mac_address: string | null;
  identity: string | null;
  platform: string | null;
  version: string | null;
  board: string | null;
  interface_name: string | null;
  discovered_by: string | null;
  age: string | null;
  uptime: string | null;
}

export async function listNeighbors(deviceId: string): Promise<Neighbor[]> {
  try {
    return await api.get(`devices/${deviceId}/neighbors`).json<Neighbor[]>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export interface NeighborDiscovery {
  discover_interface_list: string | null;
  protocols: string | null;
}

export async function getNeighborDiscovery(deviceId: string): Promise<NeighborDiscovery> {
  try {
    return await api
      .get(`devices/${deviceId}/neighbor-discovery`)
      .json<NeighborDiscovery>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function setNeighborDiscovery(
  deviceId: string,
  payload: NeighborDiscovery,
): Promise<NeighborDiscovery> {
  try {
    return await api
      .put(`devices/${deviceId}/neighbor-discovery`, { json: payload })
      .json<NeighborDiscovery>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Bridge hosts ----------------

export interface BridgeHost {
  id: string | null;
  mac_address: string;
  on_interface: string | null;
  bridge: string | null;
  age: string | null;
  dynamic: boolean | null;
  external: boolean | null;
}

export async function listBridgeHosts(deviceId: string): Promise<BridgeHost[]> {
  return api.get(`devices/${deviceId}/bridge-hosts`).json<BridgeHost[]>();
}

// ---------------- Interfaces + VLANs ----------------

export interface Interface {
  id: string | null;
  name: string;
  type: string;
  running: boolean | null;
  disabled: boolean;
  mac_address: string | null;
  mtu: number | null;
  actual_mtu: number | null;
  rx_bytes: number | null;
  tx_bytes: number | null;
  comment: string | null;
}

export interface Vlan {
  id: string | null;
  name: string;
  interface: string;
  vlan_id: number;
  mtu: number | null;
  disabled: boolean;
  comment: string | null;
}

export interface VlanCreate {
  name: string;
  interface: string;
  vlan_id: number;
  mtu?: number | null;
  comment?: string | null;
}

export async function listInterfaces(deviceId: string): Promise<Interface[]> {
  return api.get(`devices/${deviceId}/interfaces`).json<Interface[]>();
}

// ---------------- Interface lists ----------------

export interface InterfaceList {
  id: string | null;
  name: string;
  include: string | null;
  exclude: string | null;
  dynamic: boolean;
  builtin: boolean;
  comment: string | null;
}

export interface InterfaceListMember {
  id: string | null;
  list: string;
  interface: string;
  dynamic: boolean;
  disabled: boolean;
  comment: string | null;
}

export async function listInterfaceLists(
  deviceId: string,
): Promise<InterfaceList[]> {
  return api
    .get(`devices/${deviceId}/interface-lists`)
    .json<InterfaceList[]>();
}

export async function listInterfaceListMembers(
  deviceId: string,
): Promise<InterfaceListMember[]> {
  return api
    .get(`devices/${deviceId}/interface-list-members`)
    .json<InterfaceListMember[]>();
}
export async function listVlans(deviceId: string): Promise<Vlan[]> {
  return api.get(`devices/${deviceId}/vlans`).json<Vlan[]>();
}
export async function createVlan(
  deviceId: string,
  payload: VlanCreate,
): Promise<{ id: string }> {
  try {
    return await api.post(`devices/${deviceId}/vlans`, { json: payload }).json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
export async function deleteVlan(deviceId: string, vlanId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/vlans/${encodeURIComponent(vlanId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export function formatBytes(n: number | null): string {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 ? 0 : 1)} ${units[i]}`;
}
