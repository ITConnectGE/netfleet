import { api } from "@/lib/api";

export interface UnrotatedSecret {
  device_id: string;
  device_name: string;
  secret_kind: string;
  secret_identifier: string;
  secret_label: string | null;
  revealed_at: string;
  last_rotated_at: string | null;
}

export interface RiskReport {
  user_id: string;
  count: number;
  items: UnrotatedSecret[];
}

export async function fetchRiskReport(userId: string): Promise<RiskReport> {
  return api.get(`users/${userId}/risk-report`).json<RiskReport>();
}
