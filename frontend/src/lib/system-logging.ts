import { api, readErrorMessage } from "@/lib/api";

// ---------------- Types ----------------

export interface LoggingRule {
  id: string | null;
  topics: string;
  action: string;
  prefix: string | null;
  disabled: boolean;
  invalid: boolean;
  default: boolean;
}

export interface LoggingRuleCreate {
  topics: string;
  action: string;
  prefix?: string | null;
  disabled?: boolean;
}

export interface LoggingRuleUpdate {
  topics?: string;
  action?: string;
  prefix?: string | null;
  disabled?: boolean;
}

export type LoggingActionTarget = "memory" | "disk" | "echo" | "remote";

export interface LoggingAction {
  id: string | null;
  name: string;
  target: string;
  remote: string | null;
  remote_port: number | null;
  src_address: string | null;
  bsd_syslog: boolean | null;
  syslog_facility: string | null;
  syslog_severity: string | null;
  memory_lines: number | null;
  disk_lines_per_file: number | null;
  disk_file_count: number | null;
  default: boolean;
}

export interface LoggingActionCreate {
  name: string;
  target: LoggingActionTarget;
  remote?: string | null;
  remote_port?: number | null;
  src_address?: string | null;
  bsd_syslog?: boolean | null;
  syslog_facility?: string | null;
  syslog_severity?: string | null;
  memory_lines?: number | null;
}

// ---------------- API ----------------

export async function listLoggingRules(deviceId: string): Promise<LoggingRule[]> {
  return api.get(`devices/${deviceId}/logging/rules`).json<LoggingRule[]>();
}

export async function createLoggingRule(
  deviceId: string,
  payload: LoggingRuleCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/logging/rules`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateLoggingRule(
  deviceId: string,
  ruleId: string,
  payload: LoggingRuleUpdate,
): Promise<void> {
  try {
    await api.patch(
      `devices/${deviceId}/logging/rules/${encodeURIComponent(ruleId)}`,
      { json: payload },
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteLoggingRule(
  deviceId: string,
  ruleId: string,
): Promise<void> {
  try {
    await api.delete(
      `devices/${deviceId}/logging/rules/${encodeURIComponent(ruleId)}`,
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function listLoggingActions(
  deviceId: string,
): Promise<LoggingAction[]> {
  return api
    .get(`devices/${deviceId}/logging/actions`)
    .json<LoggingAction[]>();
}

export async function createLoggingAction(
  deviceId: string,
  payload: LoggingActionCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/logging/actions`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteLoggingAction(
  deviceId: string,
  actionId: string,
): Promise<void> {
  try {
    await api.delete(
      `devices/${deviceId}/logging/actions/${encodeURIComponent(actionId)}`,
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Templates ----------------

export interface LoggingTemplate {
  key: string;
  label: string;
  description: string;
  topics: string;
  action: "memory" | "disk" | "echo";
  prefix?: string;
}

/**
 * Ready-made rules for common forensic / audit scenarios. The point is
 * one-click "log X to memory" / "log X to disk" without having to
 * remember the exact topic set RouterOS exposes. Keep the list short
 * and high-signal — adding obscure templates makes the picker harder
 * to skim.
 */
export const LOGGING_TEMPLATES: LoggingTemplate[] = [
  {
    key: "firewall-drops",
    label: "Firewall drops",
    description:
      "Every packet a `drop` / `reject` firewall rule with log=yes matches. Combined with NetFleet's central inbox you'll see which rules are actually firing.",
    topics: "firewall",
    action: "memory",
    prefix: "fw-drop",
  },
  {
    key: "ssh-winbox-logins",
    label: "SSH / WinBox / API logins",
    description:
      "Login attempts (success and failure) on every management plane: SSH, WinBox, REST, RouterOS API. The classic 'who logged in last night' query.",
    topics: "account,system,!debug,!packet,!info",
    action: "disk",
    prefix: "auth",
  },
  {
    key: "dhcp-activity",
    label: "DHCP server activity",
    description:
      "DHCP lease grants, renewals and rejections. Useful when a printer ‘forgets’ its address and you need to know which lease was handed out.",
    topics: "dhcp",
    action: "memory",
  },
  {
    key: "vpn-events",
    label: "VPN connect / disconnect",
    description:
      "Tunnel up/down across L2TP, PPTP, OpenVPN, SSTP and WireGuard. The fastest way to spot a flapping branch tunnel.",
    topics: "l2tp,pptp,ovpn,sstp,ipsec,wireguard",
    action: "disk",
    prefix: "vpn",
  },
  {
    key: "wireguard-handshakes",
    label: "WireGuard handshakes",
    description:
      "WireGuard peer handshake successes and failures only — narrower than the broader VPN template, useful on routers that run a lot of WG peers.",
    topics: "wireguard",
    action: "memory",
    prefix: "wg",
  },
  {
    key: "warnings-errors-criticals",
    label: "All warnings + errors + criticals",
    description:
      "Catch-all severity bucket. Everything the box considers worth flagging — what you'd send to a syslog SIEM if you had one.",
    topics: "warning,error,critical",
    action: "disk",
  },
  {
    key: "ipsec-key-exchange",
    label: "IPsec key exchange",
    description:
      "Phase 1 / Phase 2 negotiation, SA installs and rekeys. Indispensable when troubleshooting why one site of an IPsec VPN won't come up.",
    topics: "ipsec",
    action: "memory",
    prefix: "ipsec",
  },
  {
    key: "ospf-bgp-routing",
    label: "OSPF / BGP routing changes",
    description:
      "Adjacency state changes, neighbour resets and route flaps. Apply on routers running dynamic routing protocols.",
    topics: "ospf,bgp,routing",
    action: "memory",
    prefix: "route",
  },
];
