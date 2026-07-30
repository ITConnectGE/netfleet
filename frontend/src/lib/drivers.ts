import { api } from "@/lib/api";

export interface Driver {
  vendor: string;
  display_name: string;
  capabilities: string[];
}

export async function listDrivers(): Promise<Driver[]> {
  return api.get("drivers").json<Driver[]>();
}

/** Shared react-query key so every consumer hits one cached fetch. */
export const DRIVERS_QUERY_KEY = ["drivers"] as const;

/**
 * Capabilities of the driver behind `vendor`.
 *
 * Returns `null` while the driver list is still loading, which callers must
 * distinguish from "no capabilities" — rendering an empty tab strip for a
 * moment is worse than rendering the full one and settling.
 */
export function capabilitiesFor(
  drivers: Driver[] | undefined,
  vendor: string | undefined,
): Set<string> | null {
  if (!drivers || !vendor) return null;
  const d = drivers.find((x) => x.vendor === vendor);
  return d ? new Set(d.capabilities) : new Set<string>();
}
