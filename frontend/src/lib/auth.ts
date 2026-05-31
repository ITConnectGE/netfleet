import { api, readErrorMessage } from "@/lib/api";
import { authStorage } from "@/lib/auth-storage";

export interface UserPublic {
  id: string;
  email: string;
  display_name: string | null;
  mobile_phone: string | null;
  is_admin: boolean;
  totp_enrolled: boolean;
  otp_login_enabled: boolean;
  must_change_password: boolean;
  auth_method: "local" | "oidc";
  organization_id: string;
}

export interface ProfileUpdate {
  display_name?: string | null;
  mobile_phone?: string | null;
  otp_login_enabled?: boolean;
}

export async function updateProfile(payload: ProfileUpdate): Promise<UserPublic> {
  try {
    return await api.patch("auth/me", { json: payload }).json<UserPublic>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface TokenPair {
  access_token: string;
  expires_at: string;
}

export async function changePassword(payload: ChangePasswordPayload): Promise<TokenPair> {
  try {
    const out = await api
      .post("auth/change-password", { json: payload })
      .json<TokenPair>();
    // Server revoked every refresh token + minted a new one in the cookie;
    // here we just refresh the in-memory access token so the active tab
    // keeps working without a re-login.
    authStorage.setAccessToken(out.access_token, out.expires_at);
    return out;
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export interface TotpEnrollResponse {
  secret: string;
  otpauth_uri: string;
}

export async function enrollTotpBegin(): Promise<TotpEnrollResponse> {
  try {
    return await api.post("auth/totp/enroll").json<TotpEnrollResponse>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function enrollTotpConfirm(code: string): Promise<void> {
  try {
    await api.post("auth/totp/enroll/confirm", { json: { code } });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function disableTotp(currentPassword: string): Promise<void> {
  try {
    await api.post("auth/totp/disable", { json: { current_password: currentPassword } });
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
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

export interface LoginOtpRequired {
  status: "otp_required";
  mfa_temp_token: string;
  mfa_temp_expires_at: string;
  channel: "sms" | "email";
  destination_hint: string;
}

export type LoginResult = LoginFinal | LoginMfaRequired | LoginOtpRequired;

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

export async function verifyLoginOtp(
  mfa_temp_token: string,
  code: string,
): Promise<LoginFinal> {
  try {
    const json = await api
      .post("auth/otp/verify", { json: { mfa_temp_token, code } })
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

export async function performSetup(
  payload: SetupPayload,
  bootstrapToken: string,
): Promise<void> {
  try {
    // X-Bootstrap-Token guards first-run takeover. The token is delivered
    // out-of-band by the installer (URL fragment, never sent to the server
    // on the initial GET), so it never lands in access logs or proxy caches.
    await api
      .post("setup", {
        json: payload,
        headers: { "X-Bootstrap-Token": bootstrapToken },
      })
      .json();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
