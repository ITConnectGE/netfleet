import { api } from "@/lib/api";
import { authStorage } from "@/lib/auth-storage";

// ---------------- shared ----------------

export interface DateRange {
  ts_from: string; // ISO
  ts_to: string;   // ISO
}

function range(params: object): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(params as Record<string, unknown>)) {
    if (typeof v === "string" && v !== "") out[k] = v;
  }
  return out;
}

// ---------------- User activity ----------------

export interface UserActivityRow {
  ts: string;
  user_id: string | null;
  user_email: string | null;
  section: string;
  action: string;
  outcome: "ok" | "denied" | "failed";
  device_id: string | null;
  device_name: string | null;
  site_id: string | null;
  site_name: string | null;
  tenant_name: string | null;
  ip_address: string | null;
}

export interface UserActivitySummary {
  user_id: string | null;
  user_email: string | null;
  total: number;
  writes: number;
  failures: number;
  sections_touched: number;
  devices_touched: number;
}

export interface UserActivityReport {
  range_from: string;
  range_to: string;
  rows: UserActivityRow[];
  summary: UserActivitySummary[];
  truncated: boolean;
}

export async function userActivityReport(
  params: DateRange & { user_id?: string },
): Promise<UserActivityReport> {
  return api
    .get("reports/user-activity", { searchParams: range(params) })
    .json<UserActivityReport>();
}

// ---------------- Device activity ----------------

export interface DeviceActivityRow {
  ts: string;
  user_email: string | null;
  section: string;
  action: string;
  outcome: "ok" | "denied" | "failed";
  ip_address: string | null;
  request_payload: Record<string, unknown> | null;
  error_message: string | null;
}

export interface DeviceActivityReport {
  device_id: string;
  device_name: string | null;
  range_from: string;
  range_to: string;
  rows: DeviceActivityRow[];
  truncated: boolean;
}

export async function deviceActivityReport(
  params: DateRange & { device_id: string },
): Promise<DeviceActivityReport> {
  return api
    .get("reports/device-activity", { searchParams: range(params) })
    .json<DeviceActivityReport>();
}

// ---------------- Secret access ----------------

export interface SecretAccessRow {
  ts: string;
  user_email: string | null;
  device_id: string;
  device_name: string | null;
  secret_kind: string;
  secret_identifier: string;
  secret_label: string | null;
  last_rotation_ts: string | null;
  rotated_since_reveal: boolean;
  ip_address: string | null;
  justification: string | null;
}

export interface SecretAccessReport {
  range_from: string;
  range_to: string;
  rows: SecretAccessRow[];
  unrotated_count: number;
}

export async function secretAccessReport(
  params: DateRange & { user_id?: string },
): Promise<SecretAccessReport> {
  return api
    .get("reports/secret-access", { searchParams: range(params) })
    .json<SecretAccessReport>();
}

// ---------------- Changes ----------------

export interface ChangeRow {
  ts: string;
  user_email: string | null;
  section: string;
  action: string;
  outcome: "ok" | "denied" | "failed";
  device_id: string | null;
  device_name: string | null;
  request_payload: Record<string, unknown> | null;
}

export interface ChangeReport {
  range_from: string;
  range_to: string;
  rows: ChangeRow[];
  by_section: Record<string, number>;
  by_user: Record<string, number>;
  truncated: boolean;
}

export async function changeReport(
  params: DateRange & { section?: string },
): Promise<ChangeReport> {
  return api
    .get("reports/changes", { searchParams: range(params) })
    .json<ChangeReport>();
}

// ---------------- CSV download ----------------

/** Build a relative CSV URL — caller appends the access token via Authorization header. */
function csvUrl(
  endpoint: string,
  params: DateRange & Record<string, string | undefined>,
): string {
  const sp = new URLSearchParams();
  sp.set("format", "csv");
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") sp.set(k, v);
  }
  return `/api/v1/reports/${endpoint}?${sp.toString()}`;
}

// ---------------- User & roles (P21 #15.7) ----------------

export interface UserRoleAssignmentRow {
  role_id: string;
  role_name: string;
  scope_type: "organization" | "tenant" | "site" | "device";
  scope_id: string | null;
  scope_label: string | null;
}

export interface UserRoleSummary {
  user_id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  is_active: boolean;
  totp_enrolled: boolean;
  otp_login_enabled: boolean;
  assignments: UserRoleAssignmentRow[];
  permission_count: number;
}

export interface RoleSummary {
  role_id: string;
  role_name: string;
  is_system: boolean;
  description: string | null;
  user_count: number;
  permissions: string[];
}

export interface UserRolesReport {
  users: UserRoleSummary[];
  roles: RoleSummary[];
}

export async function userRolesReport(): Promise<UserRolesReport> {
  return api.get("reports/user-roles").json<UserRolesReport>();
}

export async function downloadReportCsv(
  endpoint: "user-activity" | "device-activity" | "secret-access" | "changes",
  params: DateRange & Record<string, string | undefined>,
  filenameHint: string,
): Promise<void> {
  const token = authStorage.getAccessToken();
  const res = await fetch(csvUrl(endpoint, params), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`download failed: HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const dispo = res.headers.get("Content-Disposition") ?? "";
  const match = dispo.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? `${filenameHint}.csv`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
