import { api, readErrorMessage } from "@/lib/api";
import type { ScopeKind } from "@/lib/access";

export type AccessRequestStatus = "pending" | "approved" | "denied" | "cancelled";

export interface AccessRequestGrant {
  role_id: string;
  role_name: string;
  assignment_id: string;
  expires_at: string | null;
}

export interface AccessRequestPublic {
  id: string;
  organization_id: string;
  requester_user_id: string;
  requester_email: string;
  requester_display_name: string | null;
  scope_type: ScopeKind;
  scope_id: string | null;
  scope_label: string | null;
  reason: string | null;
  status: AccessRequestStatus;
  created_at: string;
  updated_at: string;
  decided_at: string | null;
  decided_by_user_id: string | null;
  decided_by_email: string | null;
  granted_expires_at: string | null;
  decision_note: string | null;
  grants: AccessRequestGrant[];
}

export interface AccessRequestCreate {
  scope_type: "tenant" | "site" | "device";
  scope_id: string;
  reason?: string | null;
}

export interface AccessRequestApprove {
  role_ids: string[];
  expires_at?: string | null;
  note?: string | null;
}

export interface AccessRequestDeny {
  note?: string | null;
}

export interface DirectoryDeviceNode {
  id: string;
  name: string;
  has_access: boolean;
}

export interface DirectorySiteNode {
  id: string;
  name: string;
  has_access: boolean;
  devices: DirectoryDeviceNode[];
}

export interface DirectoryTenantNode {
  id: string;
  name: string;
  has_access: boolean;
  sites: DirectorySiteNode[];
}

export interface DirectoryReport {
  tenants: DirectoryTenantNode[];
}

export async function createAccessRequest(
  payload: AccessRequestCreate,
): Promise<AccessRequestPublic> {
  try {
    return await api
      .post("access-requests", { json: payload })
      .json<AccessRequestPublic>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function listAccessRequests(
  status?: AccessRequestStatus,
): Promise<AccessRequestPublic[]> {
  const searchParams = status ? { status } : undefined;
  return api
    .get("access-requests", { searchParams })
    .json<AccessRequestPublic[]>();
}

export async function getAccessRequest(id: string): Promise<AccessRequestPublic> {
  return api.get(`access-requests/${id}`).json<AccessRequestPublic>();
}

export async function approveAccessRequest(
  id: string,
  payload: AccessRequestApprove,
): Promise<AccessRequestPublic> {
  try {
    return await api
      .post(`access-requests/${id}/approve`, { json: payload })
      .json<AccessRequestPublic>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function denyAccessRequest(
  id: string,
  payload: AccessRequestDeny,
): Promise<AccessRequestPublic> {
  try {
    return await api
      .post(`access-requests/${id}/deny`, { json: payload })
      .json<AccessRequestPublic>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function cancelAccessRequest(
  id: string,
): Promise<AccessRequestPublic> {
  try {
    return await api
      .post(`access-requests/${id}/cancel`)
      .json<AccessRequestPublic>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function fetchDirectory(): Promise<DirectoryReport> {
  return api.get("access-requests/-/directory").json<DirectoryReport>();
}
