import { api, readErrorMessage } from "@/lib/api";

export interface UfwRule {
  action: string; // allow | deny | reject | limit
  direction: string; // in | out | fwd
  /** ufw's "To" column — what is being opened on this host. */
  destination: string;
  /** ufw's "From" column — the remote. */
  source: string;
  ip_version: "v4" | "v6" | "both";
  /** Position in `ufw status numbered`. Null when the firewall is inactive. */
  position: number | null;
  position_v6: number | null;
  interface: string | null;
  app: string | null;
  comment: string | null;
  /** The `ufw show added` line — the stable handle for a later delete. */
  spec: string | null;
}

/**
 * A rule switched off in NetFleet.
 *
 * ufw has no disabled state, so this rule is *not on the host* — it will not
 * appear in `ufw status` there. NetFleet is holding it, along with where to
 * put it back.
 */
export interface UfwDisabledRule {
  id: string;
  spec: string;
  position: number | null;
  disabled_at: string;
  action: string;
  direction: string;
  destination: string;
  source: string;
  interface: string | null;
  comment: string | null;
}

export interface UfwStatus {
  installed: boolean;
  active: boolean;
  logging: string | null;
  default_incoming: string | null;
  default_outgoing: string | null;
  default_routed: string | null;
  rules: UfwRule[];
  app_profiles: string[];
  /**
   * Rules came from `ufw show added` rather than the numbered table, because
   * ufw is switched off and `ufw status` lists nothing in that state.
   */
  rules_from_added: boolean;
  /** Rules NetFleet is holding off the host. Not visible in `ufw status`. */
  disabled_rules: UfwDisabledRule[];
}

export async function getUfwStatus(deviceId: string): Promise<UfwStatus> {
  return api
    .get(`devices/${deviceId}/firewall/ufw`, { timeout: 45_000 })
    .json<UfwStatus>();
}

export type ChangeGuardState =
  | "armed"
  | "confirmed"
  | "rolled_back"
  | "expired";

/**
 * A dead-man timer running *on the host*, protecting a firewall change.
 *
 * Normally invisible: a guarded change disarms its own guard the moment a
 * fresh connection proves the host is still reachable. One shows up here only
 * when that verification could not settle — which is exactly when someone
 * needs to decide whether to keep the change or drop it.
 */
export interface ChangeGuard {
  id: string;
  device_id: string;
  kind: string;
  state: ChangeGuardState;
  window_seconds: number;
  armed_at: string;
  expires_at: string;
  resolved_at: string | null;
  detail: string | null;
}

export interface UfwRuleCreate {
  action: "allow" | "deny" | "reject" | "limit";
  direction: "in" | "out" | "fwd";
  from_address?: string | null;
  to_address?: string | null;
  port?: string | null;
  protocol?: "tcp" | "udp" | null;
  interface?: string | null;
  comment?: string | null;
  /** 1-based, matching `ufw insert`. Omit to append. */
  position?: number | null;
}

export interface UfwWriteResult {
  command: string;
  guard: ChangeGuard;
}

export async function createUfwRule(
  deviceId: string,
  rule: UfwRuleCreate,
): Promise<UfwWriteResult> {
  try {
    return await api
      .post(`devices/${deviceId}/firewall/ufw/rules`, {
        json: rule,
        // A guarded write arms a timer, applies, then opens a fresh
        // connection to verify. Three round trips to a possibly-slow host.
        timeout: 120_000,
      })
      .json<UfwWriteResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

/**
 * Delete by specification, never by position: ufw renumbers on every delete,
 * so a position read when the page rendered can address a different rule by
 * the time the click lands.
 */
export async function deleteUfwRule(
  deviceId: string,
  spec: string,
  force = false,
): Promise<UfwWriteResult> {
  try {
    return await api
      .post(`devices/${deviceId}/firewall/ufw/rules/delete`, {
        json: { spec, force },
        timeout: 120_000,
      })
      .json<UfwWriteResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function editUfwRule(
  deviceId: string,
  spec: string,
  rule: UfwRuleCreate,
  force = false,
): Promise<UfwWriteResult> {
  try {
    return await api
      .post(`devices/${deviceId}/firewall/ufw/rules/edit`, {
        json: { ...rule, spec, force },
        timeout: 120_000,
      })
      .json<UfwWriteResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

/** ufw is first-match, so this changes behaviour even though nothing is
 * added or removed. */
export async function moveUfwRule(
  deviceId: string,
  spec: string,
  position: number,
  force = false,
): Promise<UfwWriteResult> {
  try {
    return await api
      .post(`devices/${deviceId}/firewall/ufw/rules/move`, {
        json: { spec, position, force },
        timeout: 120_000,
      })
      .json<UfwWriteResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

/**
 * Switch a rule off: remove it from the host, remember it in NetFleet. There
 * is no ufw command for this — a rule is in the ruleset or it is not.
 */
export async function disableUfwRule(
  deviceId: string,
  spec: string,
  force = false,
): Promise<UfwWriteResult> {
  try {
    return await api
      .post(`devices/${deviceId}/firewall/ufw/rules/disable`, {
        json: { spec, force },
        timeout: 120_000,
      })
      .json<UfwWriteResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function enableUfwRule(
  deviceId: string,
  disabledRuleId: string,
  force = false,
): Promise<UfwWriteResult> {
  try {
    return await api
      .post(
        `devices/${deviceId}/firewall/ufw/disabled/${disabledRuleId}/enable`,
        { searchParams: { force }, timeout: 120_000 },
      )
      .json<UfwWriteResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export interface UfwSuggestedRule {
  action: string;
  direction: string;
  port: string | null;
  protocol: string | null;
  from_address: string | null;
  comment: string | null;
}

/**
 * Everything the enable dialog needs to be specific rather than generic.
 *
 * `covered` decides which of two states it shows. A dialog that looks the
 * same whether or not the host is safe teaches people to click through it.
 */
export interface UfwEnablePreflight {
  already_active: boolean;
  /** Null when $SSH_CONNECTION was unavailable — the fix cannot be pre-filled. */
  management_address: string | null;
  management_port: number | null;
  default_incoming: string | null;
  covered: boolean;
  covering_rule_spec: string | null;
  covering_rule_summary: string | null;
  suggested_rule: UfwSuggestedRule | null;
}

export async function getEnablePreflight(
  deviceId: string,
): Promise<UfwEnablePreflight> {
  return api
    .get(`devices/${deviceId}/firewall/ufw/enable-preflight`, {
      timeout: 45_000,
    })
    .json<UfwEnablePreflight>();
}

export async function setUfwEnabled(
  deviceId: string,
  opts: { enabled: boolean; allowManagement?: boolean; force?: boolean },
): Promise<UfwWriteResult> {
  try {
    return await api
      .post(`devices/${deviceId}/firewall/ufw/enabled`, {
        json: {
          enabled: opts.enabled,
          allow_management: opts.allowManagement ?? false,
          force: opts.force ?? false,
        },
        timeout: 120_000,
      })
      .json<UfwWriteResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function listPendingGuards(
  deviceId: string,
): Promise<ChangeGuard[]> {
  return api.get(`devices/${deviceId}/firewall/guards`).json<ChangeGuard[]>();
}

export async function confirmGuard(
  deviceId: string,
  guardId: string,
): Promise<ChangeGuard> {
  return api
    .post(`devices/${deviceId}/firewall/guards/${guardId}/confirm`)
    .json<ChangeGuard>();
}

export async function rollbackGuard(
  deviceId: string,
  guardId: string,
): Promise<ChangeGuard> {
  return api
    .post(`devices/${deviceId}/firewall/guards/${guardId}/rollback`)
    .json<ChangeGuard>();
}
