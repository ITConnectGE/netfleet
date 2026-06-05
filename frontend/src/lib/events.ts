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

// FastAPI's `list[Enum]` query parameter wants the key REPEATED
// (?severity=critical&severity=error), not comma-joined. ky's
// `searchParams` flattens arrays into a single comma-separated value,
// so we build URLSearchParams manually here.
function buildSearch(params: ListEventsParams): URLSearchParams {
  const sp = new URLSearchParams();
  if (params.severity) {
    for (const s of params.severity) sp.append("severity", s);
  }
  if (params.device_id) sp.set("device_id", params.device_id);
  if (params.tenant_id) sp.set("tenant_id", params.tenant_id);
  if (params.site_id) sp.set("site_id", params.site_id);
  if (params.acknowledged !== undefined)
    sp.set("acknowledged", String(params.acknowledged));
  if (params.since) sp.set("since", params.since);
  if (params.until) sp.set("until", params.until);
  if (params.search) sp.set("search", params.search);
  if (params.limit !== undefined) sp.set("limit", String(params.limit));
  if (params.offset !== undefined) sp.set("offset", String(params.offset));
  return sp;
}

export async function listEvents(params: ListEventsParams = {}): Promise<EventListResponse> {
  try {
    return await api.get("events", { searchParams: buildSearch(params) }).json<EventListResponse>();
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

/** Unacknowledged-event count per site, broken down by severity. The
 *  fleet map calls this to flip a site's pin to dark red whenever the
 *  `critical` slot is > 0. */
export async function eventsPerSiteSummary(): Promise<
  Record<string, Record<Severity, number>>
> {
  return api
    .get("events/per-site-summary")
    .json<Record<string, Record<Severity, number>>>();
}
