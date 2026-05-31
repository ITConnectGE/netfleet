import { api, readErrorMessage } from "@/lib/api";
import type { AssignmentScope } from "@/lib/roles";

export interface UserListItem {
  id: string;
  email: string;
  display_name: string | null;
  mobile_phone: string | null;
  is_active: boolean;
  is_admin: boolean;
  totp_enrolled: boolean;
  otp_login_enabled: boolean;
  must_change_password: boolean;
  auth_method: "local" | "oidc";
  last_login_at: string | null;
  created_at: string;
  assignment_count: number;
}

export interface UserCreate {
  email: string;
  display_name: string;
  /**
   * Optional from P21 Stage 3 on. When omitted, the backend generates
   * a 16-character random password and forces the user through a
   * change-password flow on first login.
   */
  password?: string | null;
  mobile_phone?: string | null;
  is_admin?: boolean;
  /** Org-scope role assignments minted at invite time. */
  role_ids?: string[];
}

export interface UserUpdate {
  display_name?: string;
  mobile_phone?: string | null;
  is_active?: boolean;
  is_admin?: boolean;
}

export interface UserInviteResponse {
  user: UserListItem;
  /**
   * Plaintext returned exactly once when the password was auto-
   * generated. Show it to the inviter, then drop it on the floor; the
   * server has only the hash from this point on.
   */
  generated_password: string | null;
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

export async function createUser(payload: UserCreate): Promise<UserInviteResponse> {
  try {
    return await api.post("users", { json: payload }).json<UserInviteResponse>();
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
