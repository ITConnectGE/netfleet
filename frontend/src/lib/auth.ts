import { api, readErrorMessage } from "@/lib/api";
import { authStorage } from "@/lib/auth-storage";

export interface UserPublic {
  id: string;
  email: string;
  display_name: string | null;
  is_admin: boolean;
  totp_enrolled: boolean;
  auth_method: "local" | "oidc";
  organization_id: string;
}

export interface LoginFinal {
  status: "ok";
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: UserPublic;
}

export interface LoginMfaRequired {
  status: "mfa_required";
  mfa_temp_token: string;
  mfa_temp_expires_at: string;
}

export type LoginResult = LoginFinal | LoginMfaRequired;

export async function login(email: string, password: string): Promise<LoginResult> {
  try {
    const json = await api
      .post("auth/login", { json: { email, password } })
      .json<LoginResult>();
    if (json.status === "ok") {
      authStorage.setAccessToken(json.access_token, json.expires_at);
    }
    return json;
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function verifyTotp(
  mfa_temp_token: string,
  code: string,
): Promise<LoginFinal> {
  try {
    const json = await api
      .post("auth/totp/verify", { json: { mfa_temp_token, code } })
      .json<LoginFinal>();
    authStorage.setAccessToken(json.access_token, json.expires_at);
    return json;
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function logout(): Promise<void> {
  try {
    await api.post("auth/logout");
  } finally {
    authStorage.clear();
  }
}

export async function fetchMe(): Promise<UserPublic | null> {
  try {
    return await api.get("auth/me").json<UserPublic>();
  } catch {
    return null;
  }
}

export async function fetchSetupStatus(): Promise<{ setup_complete: boolean }> {
  return api.get("setup/status").json<{ setup_complete: boolean }>();
}

export interface SetupPayload {
  organization_name: string;
  organization_slug: string;
  admin_email: string;
  admin_display_name: string;
  admin_password: string;
}

export async function performSetup(payload: SetupPayload): Promise<void> {
  try {
    await api.post("setup", { json: payload }).json();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
