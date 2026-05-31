import { api } from "@/lib/api";

export type ScopeKind = "organization" | "tenant" | "site" | "device";

export interface AccessEntry {
  user_id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  role_id: string | null;
  role_name: string | null;
  source_scope_type: ScopeKind | null;
  source_scope_id: string | null;
  source_scope_label: string | null;
}

export interface AccessReport {
  scope_type: ScopeKind;
  scope_id: string | null;
  scope_label: string;
  entries: AccessEntry[];
}

export interface UserScopeGrant {
  role_id: string | null;
  role_name: string | null;
  via_scope_type: ScopeKind | null;
  via_scope_id: string | null;
  via_scope_label: string | null;
}

export interface UserAccessDeviceNode {
  device_id: string;
  device_name: string;
  grants: UserScopeGrant[];
}

export interface UserAccessSiteNode {
  site_id: string;
  site_name: string;
  grants: UserScopeGrant[];
  devices: UserAccessDeviceNode[];
}

export interface UserAccessTenantNode {
  tenant_id: string;
  tenant_name: string;
  grants: UserScopeGrant[];
  sites: UserAccessSiteNode[];
}

export interface PermissionTuple {
  section: string;
  action: string;
}

export interface UserAccessMap {
  user_id: string;
  tenants: UserAccessTenantNode[];
  permissions: PermissionTuple[];
}

export async function fetchTenantAccess(tenantId: string): Promise<AccessReport> {
  return api.get(`access/tenant/${tenantId}`).json<AccessReport>();
}

export async function fetchSiteAccess(siteId: string): Promise<AccessReport> {
  return api.get(`access/site/${siteId}`).json<AccessReport>();
}

export async function fetchDeviceAccess(deviceId: string): Promise<AccessReport> {
  return api.get(`access/device/${deviceId}`).json<AccessReport>();
}

export async function fetchUserAccessMap(userId: string): Promise<UserAccessMap> {
  return api.get(`access/user/${userId}`).json<UserAccessMap>();
}
