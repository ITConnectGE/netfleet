import { api, readErrorMessage } from "@/lib/api";

export type PermissionAction = "read" | "write" | "execute";
export type AssignmentScope = "organization" | "tenant" | "site" | "device";

export interface Permission {
  id: string;
  section: string;
  action: PermissionAction;
}

export interface Role {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permissions: Permission[];
  assignment_count: number;
  created_at: string;
  updated_at: string;
}

export interface SectionInfo {
  section: string;
  actions: PermissionAction[];
  kind: "app" | "driver";
}

export interface RoleCreate {
  name: string;
  description?: string | null;
  permissions: { section: string; action: PermissionAction }[];
}

export interface RoleUpdate {
  name?: string;
  description?: string | null;
  permissions?: { section: string; action: PermissionAction }[];
}

export async function listSections(): Promise<SectionInfo[]> {
  return api.get("roles/sections").json<SectionInfo[]>();
}

export async function listRoles(): Promise<Role[]> {
  return api.get("roles").json<Role[]>();
}

export async function createRole(payload: RoleCreate): Promise<Role> {
  try {
    return await api.post("roles", { json: payload }).json<Role>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateRole(id: string, payload: RoleUpdate): Promise<Role> {
  try {
    return await api.patch(`roles/${id}`, { json: payload }).json<Role>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteRole(id: string): Promise<void> {
  try {
    await api.delete(`roles/${id}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
