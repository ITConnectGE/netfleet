import { api, readErrorMessage } from "@/lib/api";

export interface BulkResult {
  device_id: string;
  device_name: string | null;
  status: "ok" | "failed" | "skipped";
  error: string | null;
}

export interface BulkPasswordResetResponse {
  total: number;
  succeeded: number;
  failed: number;
  skipped: number;
  results: BulkResult[];
}

export async function bulkResetDeviceUserPassword(
  deviceIds: string[],
  username: string,
  newPassword: string,
): Promise<BulkPasswordResetResponse> {
  try {
    return await api
      .post("bulk/device-users/password-reset", {
        json: {
          device_ids: deviceIds,
          username,
          new_password: newPassword,
        },
        timeout: 120_000,
      })
      .json<BulkPasswordResetResponse>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
