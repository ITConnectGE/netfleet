import { api, readErrorMessage } from "@/lib/api";

export interface FilterRule {
  id: string | null;
  chain: string;
  action: string;
  src_address: string | null;
  dst_address: string | null;
  src_address_list: string | null;
  dst_address_list: string | null;
  protocol: string | null;
  src_port: string | null;
  dst_port: string | null;
  in_interface: string | null;
  out_interface: string | null;
  connection_state: string | null;
  log: boolean;
  log_prefix: string | null;
  disabled: boolean;
  comment: string | null;
}

export interface FilterRuleCreate {
  chain: "input" | "forward" | "output";
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

export interface LogEntry {
  time: string;
  topics: string;
  message: string;
}

export async function listFilterRules(deviceId: string): Promise<FilterRule[]> {
  try {
    return await api.get(`devices/${deviceId}/firewall/filter`).json<FilterRule[]>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function createFilterRule(
  deviceId: string,
  payload: FilterRuleCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/firewall/filter`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function setFilterRuleDisabled(
  deviceId: string,
  ruleId: string,
  disabled: boolean,
): Promise<void> {
  try {
    await api.patch(`devices/${deviceId}/firewall/filter/${encodeURIComponent(ruleId)}`, {
      json: { disabled },
    });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteFilterRule(deviceId: string, ruleId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/firewall/filter/${encodeURIComponent(ruleId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

/** Reorder a filter rule. `beforeId` is the id of the rule the moved
 *  rule should land in front of — pass null to push it to the bottom. */
export async function moveFilterRule(
  deviceId: string,
  ruleId: string,
  beforeId: string | null,
): Promise<void> {
  try {
    await api.post(
      `devices/${deviceId}/firewall/filter/${encodeURIComponent(ruleId)}/move`,
      { json: { before_id: beforeId } },
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function listLogs(
  deviceId: string,
  options: { topics?: string; limit?: number } = {},
): Promise<LogEntry[]> {
  const searchParams: Record<string, string> = {};
  if (options.topics) searchParams.topics = options.topics;
  if (options.limit) searchParams.limit = String(options.limit);
  try {
    return await api.get(`devices/${deviceId}/logs`, { searchParams }).json<LogEntry[]>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
