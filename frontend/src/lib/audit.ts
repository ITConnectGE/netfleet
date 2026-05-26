import { api } from "@/lib/api";

export type AuditOutcome = "ok" | "denied" | "failed";

export interface AuditLogEntry {
  id: string;
  ts: string;
  user_id: string | null;
  user_email: string | null;
  section: string;
  action: string;
  outcome: AuditOutcome;
  device_id: string | null;
  site_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  request_payload: Record<string, unknown> | null;
  response_meta: Record<string, unknown> | null;
  error_message: string | null;
}

export interface AuditPage {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditFilters {
  user_id?: string;
  section?: string;
  action?: string;
  outcome?: AuditOutcome;
  device_id?: string;
  site_id?: string;
  ts_from?: string;
  ts_to?: string;
  limit?: number;
  offset?: number;
}

export async function queryAudit(filters: AuditFilters = {}): Promise<AuditPage> {
  const searchParams: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") searchParams[k] = String(v);
  }
  return api.get("audit", { searchParams }).json<AuditPage>();
}
