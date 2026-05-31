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

// ---------------- Address list ----------------

export interface BulkAddressListAddRequest {
  device_ids: string[];
  list_name: string;
  address: string;
  timeout?: string | null;
  comment?: string | null;
}

export interface BulkAddressListAddResponse {
  total: number;
  succeeded: number;
  failed: number;
  skipped: number;
  results: BulkResult[];
}

export async function bulkAddressListAdd(
  payload: BulkAddressListAddRequest,
): Promise<BulkAddressListAddResponse> {
  try {
    return await api
      .post("bulk/firewall/address-list/add", {
        json: payload,
        timeout: 120_000,
      })
      .json<BulkAddressListAddResponse>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Firewall filter ----------------

export interface BulkFilterRule {
  chain: string;
  action: string;
  src_address?: string | null;
  dst_address?: string | null;
  src_address_list?: string | null;
  dst_address_list?: string | null;
  protocol?: string | null;
  src_port?: string | null;
  dst_port?: string | null;
  in_interface?: string | null;
  out_interface?: string | null;
  connection_state?: string | null;
  log?: boolean;
  log_prefix?: string | null;
  disabled?: boolean;
  comment?: string | null;
}

export interface BulkFirewallFilterRequest {
  device_ids: string[];
  rule: BulkFilterRule;
}

export interface BulkFirewallFilterResponse {
  total: number;
  succeeded: number;
  failed: number;
  skipped: number;
  results: BulkResult[];
}

export async function bulkFirewallFilterAdd(
  payload: BulkFirewallFilterRequest,
): Promise<BulkFirewallFilterResponse> {
  try {
    return await api
      .post("bulk/firewall/filter/add", {
        json: payload,
        timeout: 120_000,
      })
      .json<BulkFirewallFilterResponse>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
