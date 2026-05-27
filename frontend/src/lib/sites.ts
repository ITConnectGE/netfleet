import { api, readErrorMessage } from "@/lib/api";

export interface Site {
  id: string;
  organization_id: string;
  tenant_id: string;
  tenant_name: string | null;
  name: string;
  slug: string;
  address: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  notes: string | null;
  device_count: number;
  created_at: string;
  updated_at: string;
}

export interface SiteCreate {
  tenant_id: string;
  name: string;
  slug: string;
  address?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  notes?: string | null;
}

export interface SiteUpdate {
  name?: string;
  address?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  notes?: string | null;
  tenant_id?: string;
}

export async function listSites(tenantId?: string): Promise<Site[]> {
  const searchParams = tenantId ? { tenant_id: tenantId } : undefined;
  return api.get("sites", { searchParams }).json<Site[]>();
}

export async function getSite(id: string): Promise<Site> {
  return api.get(`sites/${id}`).json<Site>();
}

export async function createSite(payload: SiteCreate): Promise<Site> {
  try {
    return await api.post("sites", { json: payload }).json<Site>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function updateSite(id: string, payload: SiteUpdate): Promise<Site> {
  try {
    return await api.patch(`sites/${id}`, { json: payload }).json<Site>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteSite(id: string): Promise<void> {
  try {
    await api.delete(`sites/${id}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
