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

export async function testSms(to: string, content: string): Promise<SmsTestResult> {
  try {
    return await api
      .post("settings/sms/test", { json: { to, content } })
      .json<SmsTestResult>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
