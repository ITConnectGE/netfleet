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
