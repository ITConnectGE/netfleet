import { api, readErrorMessage } from "@/lib/api";
import type { AssignmentScope } from "@/lib/roles";

export interface UserListItem {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  totp_enrolled: boolean;
  auth_method: "local" | "oidc";
  last_login_at: string | null;
  created_at: string;
  assignment_count: number;
}

export interface UserCreate {
  email: string;
  display_name: string;
  password: string;
  is_admin?: boolean;
}

export interface UserUpdate {
  display_name?: string;
  is_active?: boolean;
  is_admin?: boolean;
}

export interface Assignment {
  id: string;
  user_id: string;
  role_id: string;
  role_name: string;
  scope_type: AssignmentScope;
  scope_id: string | null;
  scope_label: string | null;
  created_at: string;
}

export interface AssignmentCreate {
  role_id: string;
  scope_type: AssignmentScope;
  scope_id?: string | null;
}

export async function listUsers(): Promise<UserListItem[]> {
  return api.get("users").json<UserListItem[]>();
}

export async function createUser(payload: UserCreate): Promise<UserListItem> {
  try {
    return await api.post("users", { json: payload }).json<UserListItem>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateUser(id: string, payload: UserUpdate): Promise<UserListItem> {
  try {
    return await api.patch(`users/${id}`, { json: payload }).json<UserListItem>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function resetUserPassword(id: string, new_password: string): Promise<void> {
  try {
    await api.post(`users/${id}/password`, { json: { new_password } });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function listAssignments(userId: string): Promise<Assignment[]> {
  return api.get(`users/${userId}/assignments`).json<Assignment[]>();
}

export async function createAssignment(
  userId: string,
  payload: AssignmentCreate,
): Promise<Assignment> {
  try {
    return await api
      .post(`users/${userId}/assignments`, { json: payload })
      .json<Assignment>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteAssignment(userId: string, assignmentId: string): Promise<void> {
  try {
    await api.delete(`users/${userId}/assignments/${assignmentId}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
