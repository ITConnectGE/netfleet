import { api } from "@/lib/api";

export interface Driver {
  vendor: string;
  display_name: string;
  capabilities: string[];
}

export async function listDrivers(): Promise<Driver[]> {
  return api.get("drivers").json<Driver[]>();
}
