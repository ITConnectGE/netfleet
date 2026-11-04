import { api, readErrorMessage } from "@/lib/api";

export type AuditOutcome = "ok" | "denied" | "failed";

export interface AuditLogEntry {
  id: string;
  ts: string;
  user_id: string | null;
  user_email: string | null;
  user_name: string | null;
  section: string;
  action: string;
  outcome: AuditOutcome;
  device_id: string | null;
  device_name: string | null;
  site_id: string | null;
  site_name: string | null;
  ip_address: string | null;
  user_agent: string | null;
  request_payload: Record<string, unknown> | null;
  response_meta: Record<string, unknown> | null;
  error_message: string | null;
  session_id: string | null;
}

export interface AuditPage {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
  /** Sessions on this page that are still signed in. */
  active_session_ids: string[];
}

export interface AuditFilters {
  user_id?: string;
  section?: string;
  action?: string;
  outcome?: AuditOutcome;
  device_id?: string;
  site_id?: string;
  session_id?: string;
  target?: string;
  search?: string;
  ts_from?: string;
  ts_to?: string;
  limit?: number;
  offset?: number;
}

export interface AuditSession {
  session_id: string;
  user_id: string | null;
  user_email: string | null;
  user_name: string | null;
  role: string | null;
  started_at: string | null;
  last_activity_at: string | null;
  sign_in_method: string | null;
  ip_address: string | null;
  user_agent: string | null;
  active: boolean;
  expires_at: string | null;
  previous_session_id: string | null;
  next_session_id: string | null;
  entries: AuditLogEntry[];
}

export async function queryAudit(filters: AuditFilters = {}): Promise<AuditPage> {
  const searchParams: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") searchParams[k] = String(v);
  }
  return api.get("audit", { searchParams }).json<AuditPage>();
}

export async function getAuditSession(id: string): Promise<AuditSession> {
  try {
    return await api.get(`audit/sessions/${id}`).json<AuditSession>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function revokeAuditSession(id: string): Promise<void> {
  try {
    await api.post(`audit/sessions/${id}/revoke`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

/** What an entry acted on, for the Target column. */
export function auditTarget(e: AuditLogEntry): string {
  if (e.device_name) return e.device_name;
  if (e.site_name) return e.site_name;
  const p = e.request_payload ?? {};
  for (const k of ["name", "email", "hostname", "username", "slug"]) {
    const v = p[k];
    if (typeof v === "string" && v) return v;
  }
  if (e.device_id) return e.device_id.slice(0, 8);
  return "—";
}

export function initials(name: string | null, email: string | null): string {
  const src = (name || email || "?").trim();
  const parts = src.split(/[\s@._-]+/).filter(Boolean);
  if (parts.length >= 2 && name) return (parts[0][0] + parts[1][0]).toUpperCase();
  return src.slice(0, 2).toUpperCase();
}

/** Browser + OS from a user-agent string: "Chrome 131 · Windows". */
export function describeClient(ua: string | null): string {
  if (!ua) return "—";
  const ver = (re: RegExp) => re.exec(ua)?.[1];
  const browser = ver(/Edg\/(\d+)/)
    ? `Edge ${ver(/Edg\/(\d+)/)}`
    : ver(/Firefox\/(\d+)/)
      ? `Firefox ${ver(/Firefox\/(\d+)/)}`
      : ver(/Chrome\/(\d+)/)
        ? `Chrome ${ver(/Chrome\/(\d+)/)}`
        : ver(/Version\/(\d+).*Safari/)
          ? `Safari ${ver(/Version\/(\d+)/)}`
          : ua.split(" ")[0];
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Mac OS X/.test(ua)
      ? "macOS"
      : /Android/.test(ua)
        ? "Android"
        : /iPhone|iPad/.test(ua)
          ? "iOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return os ? `${browser} · ${os}` : browser;
}
