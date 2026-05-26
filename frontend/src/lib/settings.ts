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
