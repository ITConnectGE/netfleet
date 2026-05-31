import { api, readErrorMessage } from "@/lib/api";

export interface PppSecret {
  id: string | null;
  name: string;
  service: string;
  profile: string | null;
  local_address: string | null;
  remote_address: string | null;
  disabled: boolean;
  comment: string | null;
}

export interface PppSecretCreate {
  name: string;
  service: string;
  password: string;
  profile?: string | null;
  local_address?: string | null;
  remote_address?: string | null;
  comment?: string | null;
}

export async function listPppSecrets(deviceId: string): Promise<PppSecret[]> {
  return api.get(`devices/${deviceId}/ppp-secrets`).json<PppSecret[]>();
}

export async function createPppSecret(
  deviceId: string,
  payload: PppSecretCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/ppp-secrets`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function resetPppSecretPassword(
  deviceId: string,
  secretId: string,
  newPassword: string,
): Promise<void> {
  try {
    await api.post(`devices/${deviceId}/ppp-secrets/${encodeURIComponent(secretId)}/password`, {
      json: { new_password: newPassword },
    });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deletePppSecret(deviceId: string, secretId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/ppp-secrets/${encodeURIComponent(secretId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function revealPppSecret(
  deviceId: string,
  secretId: string,
  justification: string,
): Promise<{ password: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/ppp-secrets/${encodeURIComponent(secretId)}/reveal`, {
        json: { justification },
      })
      .json<{ password: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- WireGuard ----------------

export interface WgInterface {
  id: string | null;
  name: string;
  listen_port: number | null;
  public_key: string | null;
  mtu: number | null;
  disabled: boolean;
  comment: string | null;
}

export interface WgInterfaceCreate {
  name: string;
  listen_port?: number | null;
  private_key?: string | null;
  mtu?: number | null;
  comment?: string | null;
}

export interface WgPeer {
  id: string | null;
  interface: string;
  public_key: string | null;
  allowed_address: string | null;
  endpoint_address: string | null;
  endpoint_port: number | null;
  persistent_keepalive: number | null;
  disabled: boolean;
  comment: string | null;
}

export interface WgPeerCreate {
  interface: string;
  public_key: string;
  preshared_key?: string | null;
  allowed_address?: string | null;
  endpoint_address?: string | null;
  endpoint_port?: number | null;
  persistent_keepalive?: number | null;
  comment?: string | null;
}

export interface WgConfigRequest {
  server_endpoint: string;
  server_endpoint_port: number;
  client_address: string;
  client_dns?: string | null;
  allowed_ips: string;
  persistent_keepalive?: number | null;
}

export async function listWgInterfaces(deviceId: string): Promise<WgInterface[]> {
  return api.get(`devices/${deviceId}/wireguard/interfaces`).json<WgInterface[]>();
}

export async function createWgInterface(
  deviceId: string,
  payload: WgInterfaceCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/wireguard/interfaces`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteWgInterface(deviceId: string, ifaceId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/wireguard/interfaces/${encodeURIComponent(ifaceId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function listWgPeers(deviceId: string, ifaceName?: string): Promise<WgPeer[]> {
  const searchParams = ifaceName ? { interface: ifaceName } : undefined;
  return api.get(`devices/${deviceId}/wireguard/peers`, { searchParams }).json<WgPeer[]>();
}

export async function createWgPeer(
  deviceId: string,
  payload: WgPeerCreate,
): Promise<{ id: string; preshared_key: string | null }> {
  try {
    return await api
      .post(`devices/${deviceId}/wireguard/peers`, { json: payload })
      .json<{ id: string; preshared_key: string | null }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteWgPeer(deviceId: string, peerId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/wireguard/peers/${encodeURIComponent(peerId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function revealWgPeerKeys(
  deviceId: string,
  peerId: string,
  justification: string,
): Promise<{ public_key: string | null; preshared_key: string | null }> {
  try {
    return await api
      .post(`devices/${deviceId}/wireguard/peers/${encodeURIComponent(peerId)}/reveal`, {
        json: { justification },
      })
      .json<{ public_key: string | null; preshared_key: string | null }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export interface WgEndpointSuggestion {
  address: string;
  interface: string;
  comment: string | null;
}

export interface WgSubnetSuggestion {
  cidr: string;
  interface: string;
  comment: string | null;
}

export async function listWgEndpointSuggestions(
  deviceId: string,
): Promise<WgEndpointSuggestion[]> {
  return api
    .get(`devices/${deviceId}/wireguard/-/endpoints-suggested`)
    .json<WgEndpointSuggestion[]>();
}

export async function listWgLanSubnets(
  deviceId: string,
): Promise<WgSubnetSuggestion[]> {
  return api
    .get(`devices/${deviceId}/wireguard/-/lan-subnets-suggested`)
    .json<WgSubnetSuggestion[]>();
}

export async function downloadWgClientConfig(
  deviceId: string,
  peerId: string,
  payload: WgConfigRequest,
): Promise<{ filename: string; text: string }> {
  try {
    const response = await api.post(
      `devices/${deviceId}/wireguard/peers/${encodeURIComponent(peerId)}/config`,
      { json: payload },
    );
    const text = await response.text();
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    return { filename: match?.[1] ?? `wg-${peerId}.conf`, text };
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

