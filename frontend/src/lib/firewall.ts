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
  bytes_count: number | null;
  packets_count: number | null;
  disabled: boolean;
  comment: string | null;
}

export interface FilterRuleUpdate {
  disabled?: boolean;
  log?: boolean;
  log_prefix?: string | null;
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

export async function updateFilterRule(
  deviceId: string,
  ruleId: string,
  payload: FilterRuleUpdate,
): Promise<void> {
  try {
    await api.patch(
      `devices/${deviceId}/firewall/filter/${encodeURIComponent(ruleId)}`,
      { json: payload },
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function resetFilterRuleCounters(
  deviceId: string,
  ruleId: string,
): Promise<void> {
  try {
    await api.post(
      `devices/${deviceId}/firewall/filter/${encodeURIComponent(ruleId)}/reset-counters`,
    );
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

// ---------------- NAT ----------------

export interface NatRule {
  id: string | null;
  chain: string;
  action: string;
  src_address: string | null;
  dst_address: string | null;
  dst_port: string | null;
  protocol: string | null;
  to_addresses: string | null;
  to_ports: string | null;
  in_interface: string | null;
  out_interface: string | null;
  log: boolean;
  log_prefix: string | null;
  bytes_count: number | null;
  packets_count: number | null;
  disabled: boolean;
  comment: string | null;
}

export interface NatRuleCreate {
  chain: "srcnat" | "dstnat" | "output";
  action: string;
  src_address?: string | null;
  dst_address?: string | null;
  dst_port?: string | null;
  protocol?: string | null;
  to_addresses?: string | null;
  to_ports?: string | null;
  in_interface?: string | null;
  out_interface?: string | null;
  log?: boolean;
  log_prefix?: string | null;
  disabled?: boolean;
  comment?: string | null;
}

export interface NatRuleUpdate {
  disabled?: boolean;
  log?: boolean;
  log_prefix?: string | null;
}

export async function listNatRules(deviceId: string): Promise<NatRule[]> {
  try {
    return await api.get(`devices/${deviceId}/firewall/nat`).json<NatRule[]>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function createNatRule(
  deviceId: string,
  payload: NatRuleCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/firewall/nat`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateNatRule(
  deviceId: string,
  ruleId: string,
  payload: NatRuleUpdate,
): Promise<void> {
  try {
    await api.patch(
      `devices/${deviceId}/firewall/nat/${encodeURIComponent(ruleId)}`,
      { json: payload },
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteNatRule(
  deviceId: string,
  ruleId: string,
): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/firewall/nat/${encodeURIComponent(ruleId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function resetNatRuleCounters(
  deviceId: string,
  ruleId: string,
): Promise<void> {
  try {
    await api.post(
      `devices/${deviceId}/firewall/nat/${encodeURIComponent(ruleId)}/reset-counters`,
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
