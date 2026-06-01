import { api, readErrorMessage } from "@/lib/api";

export interface SmtpSettings {
  smtp_enabled: boolean;
  smtp_host: string | null;
  smtp_port: number;
  smtp_username: string | null;
  smtp_from_email: string | null;
  smtp_from_name: string | null;
  smtp_use_tls: boolean;
  smtp_use_starttls: boolean;
  has_smtp_password: boolean;
}

export interface SmtpSettingsUpdate {
  smtp_enabled?: boolean;
  smtp_host?: string | null;
  smtp_port?: number;
  smtp_username?: string | null;
  smtp_password?: string;
  smtp_from_email?: string | null;
  smtp_from_name?: string | null;
  smtp_use_tls?: boolean;
  smtp_use_starttls?: boolean;
}

export interface SmtpTestResult {
  ok: boolean;
  error: string | null;
}

export async function getSmtpSettings(): Promise<SmtpSettings> {
  return api.get("settings/smtp").json<SmtpSettings>();
}

export async function updateSmtpSettings(payload: SmtpSettingsUpdate): Promise<SmtpSettings> {
  try {
    return await api.patch("settings/smtp", { json: payload }).json<SmtpSettings>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function testSmtp(to: string): Promise<SmtpTestResult> {
  try {
    return await api.post("settings/smtp/test", { json: { to } }).json<SmtpTestResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- SMS gateway ----------------

export interface SmsSettings {
  sms_enabled: boolean;
  sms_provider: string;
  sms_api_url: string | null;
  sms_http_method: string;
  sms_body_format: string;
  sms_body_template: string | null;
  sms_auth_header_name: string | null;
  sms_auth_header_value_template: string | null;
  sms_sender: string | null;
  sms_success_status_min: number;
  sms_success_status_max: number;
  sms_success_body_contains: string | null;
  sms_timeout_seconds: number;
  has_sms_api_key: boolean;
  sms_last_test_at: string | null;
  sms_last_test_ok: boolean | null;
  sms_last_test_message: string | null;
}

export interface SmsSettingsUpdate {
  sms_enabled?: boolean;
  sms_provider?: string;
  sms_api_url?: string | null;
  sms_http_method?: string;
  sms_body_format?: string;
  sms_body_template?: string | null;
  sms_auth_header_name?: string | null;
  sms_auth_header_value_template?: string | null;
  sms_api_key?: string;
  sms_sender?: string | null;
  sms_success_status_min?: number;
  sms_success_status_max?: number;
  sms_success_body_contains?: string | null;
  sms_timeout_seconds?: number;
}

export interface SmsTestResult {
  ok: boolean;
  http_status: number | null;
  response_body: string | null;
  error: string | null;
}

export interface SmsProviderPreset {
  key: string;
  label: string;
  api_url: string;
  http_method: string;
  body_format: string;
  body_template: string;
  auth_header_name: string | null;
  auth_header_value_template: string | null;
  success_status_min: number;
  success_status_max: number;
  success_body_contains: string | null;
  notes: string | null;
}

export async function getSmsSettings(): Promise<SmsSettings> {
  return api.get("settings/sms").json<SmsSettings>();
}

export async function getSmsPresets(): Promise<SmsProviderPreset[]> {
  return api.get("settings/sms/presets").json<SmsProviderPreset[]>();
}

export async function updateSmsSettings(payload: SmsSettingsUpdate): Promise<SmsSettings> {
  try {
    return await api.patch("settings/sms", { json: payload }).json<SmsSettings>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Org info ----------------

export interface OrgInfo {
  netfleet_external_ips: string | null;
}

export async function getOrgInfo(): Promise<OrgInfo> {
  return api.get("settings/org-info").json<OrgInfo>();
}

export async function updateOrgInfo(payload: OrgInfo): Promise<OrgInfo> {
  try {
    return await api.patch("settings/org-info", { json: payload }).json<OrgInfo>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- System backup ----------------

export interface SystemBackupBundle {
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface SystemBackupListResponse {
  bundles: SystemBackupBundle[];
  used_bytes: number;
  free_bytes: number;
}

export async function listSystemBackups(): Promise<SystemBackupListResponse> {
  return api.get("settings/system-backup").json<SystemBackupListResponse>();
}

export async function createSystemBackup(): Promise<SystemBackupBundle> {
  try {
    return await api.post("settings/system-backup", { timeout: 600_000 }).json<SystemBackupBundle>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteSystemBackup(filename: string): Promise<void> {
  try {
    await api.delete(`settings/system-backup/${encodeURIComponent(filename)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function testSms(to: string, content: string): Promise<SmsTestResult> {
  try {
    return await api
      .post("settings/sms/test", { json: { to, content } })
      .json<SmsTestResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

// ---------------- Authorization (OIDC + MFA toggles) ----------------

export interface AuthSettings {
  microsoft_oidc_enabled: boolean;
  microsoft_oidc_tenant_id: string | null;
  microsoft_oidc_client_id: string | null;
  has_microsoft_oidc_client_secret: boolean;

  google_oidc_enabled: boolean;
  google_oidc_client_id: string | null;
  has_google_oidc_client_secret: boolean;

  mfa_totp_enabled: boolean;
  mfa_sms_otp_enabled: boolean;
  mfa_email_otp_enabled: boolean;

  microsoft_redirect_uri: string;
  google_redirect_uri: string;
}

export interface AuthSettingsUpdate {
  microsoft_oidc_enabled?: boolean;
  microsoft_oidc_tenant_id?: string | null;
  microsoft_oidc_client_id?: string | null;
  microsoft_oidc_client_secret?: string;

  google_oidc_enabled?: boolean;
  google_oidc_client_id?: string | null;
  google_oidc_client_secret?: string;

  mfa_totp_enabled?: boolean;
  mfa_sms_otp_enabled?: boolean;
  mfa_email_otp_enabled?: boolean;
}

export async function getAuthSettings(): Promise<AuthSettings> {
  return api.get("settings/authorization").json<AuthSettings>();
}

export async function updateAuthSettings(
  payload: AuthSettingsUpdate,
): Promise<AuthSettings> {
  try {
    return await api
      .patch("settings/authorization", { json: payload })
      .json<AuthSettings>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
