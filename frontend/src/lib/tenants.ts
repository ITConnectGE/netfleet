import { api, readErrorMessage } from "@/lib/api";

export interface Tenant {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  primary_contact_name: string | null;
  primary_contact_email: string | null;
  primary_contact_phone: string | null;
  site_count: number;
  device_count: number;
  created_at: string;
  updated_at: string;
}

export interface TenantCreate {
  name: string;
  slug: string;
  description?: string | null;
  primary_contact_name?: string | null;
  primary_contact_email?: string | null;
  primary_contact_phone?: string | null;
}

export type TenantUpdate = Partial<Omit<TenantCreate, "slug">>;

export async function listTenants(): Promise<Tenant[]> {
  return api.get("tenants").json<Tenant[]>();
}

export async function getTenant(id: string): Promise<Tenant> {
  return api.get(`tenants/${id}`).json<Tenant>();
}

export async function createTenant(payload: TenantCreate): Promise<Tenant> {
  try {
    return await api.post("tenants", { json: payload }).json<Tenant>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateTenant(id: string, payload: TenantUpdate): Promise<Tenant> {
  try {
    return await api.patch(`tenants/${id}`, { json: payload }).json<Tenant>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteTenant(id: string): Promise<void> {
  try {
    await api.delete(`tenants/${id}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
