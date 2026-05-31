import { api, readErrorMessage } from "@/lib/api";

export type Severity = "critical" | "error" | "warning" | "info";
export type EventSource = "polled" | "syslog";

export interface EventRow {
  id: string;
  organization_id: string;
  device_id: string;
  device_name: string | null;
  tenant_id: string | null;
  tenant_name: string | null;
  site_id: string | null;
  site_name: string | null;
  observed_at: string;
  device_time: string | null;
  severity: Severity;
  topics: string;
  message: string;
  source: EventSource;
  acknowledged_at: string | null;
  acknowledged_by_user_id: string | null;
  acknowledged_by_email: string | null;
}

export interface EventListResponse {
  rows: EventRow[];
  total: number;
  unacknowledged_total: number;
  by_severity: Record<Severity, number>;
}

export interface ListEventsParams {
  severity?: Severity[];
  device_id?: string;
  tenant_id?: string;
  site_id?: string;
  acknowledged?: boolean;
  since?: string;
  until?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

function buildSearch(params: ListEventsParams): Record<string, string | string[]> {
  const sp: Record<string, string | string[]> = {};
  if (params.severity && params.severity.length > 0) sp.severity = params.severity;
  if (params.device_id) sp.device_id = params.device_id;
  if (params.tenant_id) sp.tenant_id = params.tenant_id;
  if (params.site_id) sp.site_id = params.site_id;
  if (params.acknowledged !== undefined) sp.acknowledged = String(params.acknowledged);
  if (params.since) sp.since = params.since;
  if (params.until) sp.until = params.until;
  if (params.search) sp.search = params.search;
  if (params.limit !== undefined) sp.limit = String(params.limit);
  if (params.offset !== undefined) sp.offset = String(params.offset);
  return sp;
}

export async function listEvents(params: ListEventsParams = {}): Promise<EventListResponse> {
  try {
    return await api
      .get("events", { searchParams: buildSearch(params) as Record<string, string> })
      .json<EventListResponse>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function eventsSummary(): Promise<{
  unacknowledged_total: number;
  by_severity: Record<Severity, number>;
}> {
  return api.get("events/summary").json<{
    unacknowledged_total: number;
    by_severity: Record<Severity, number>;
  }>();
}

export async function acknowledgeEvents(ids: string[]): Promise<void> {
  try {
    await api.post("events/acknowledge", { json: { ids } });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
