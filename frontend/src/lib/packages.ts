import { api, readErrorMessage } from "@/lib/api";

export interface PackageUpdate {
  name: string;
  current_version: string | null;
  candidate_version: string | null;
  is_security: boolean;
  origin: string | null;
  architecture: string | null;
}

export interface PackageState {
  manager: string;
  updates: PackageUpdate[];
  security_count: number;
  reboot_required: boolean;
  reboot_required_by: string[];
  last_refreshed_iso: string | null;
}

export type PackageRunState =
  | "running"
  | "succeeded"
  | "failed"
  | "interrupted";

export interface PackageRun {
  id: string;
  kind: "refresh" | "upgrade";
  state: PackageRunState;
  packages: string | null;
  started_at: string;
  finished_at: string | null;
  output: string | null;
  error: string | null;
}

export async function getPackages(deviceId: string): Promise<PackageState> {
  return api
    .get(`devices/${deviceId}/packages`, { timeout: 90_000 })
    .json<PackageState>();
}

export async function listPackageRuns(deviceId: string): Promise<PackageRun[]> {
  return api.get(`devices/${deviceId}/package-runs`).json<PackageRun[]>();
}

export async function refreshPackages(deviceId: string): Promise<PackageRun> {
  try {
    return await api
      .post(`devices/${deviceId}/packages/refresh`)
      .json<PackageRun>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function upgradePackages(
  deviceId: string,
  packages: string[] = [],
  securityOnly = false,
): Promise<PackageRun> {
  try {
    return await api
      .post(`devices/${deviceId}/packages/upgrade`, {
        json: { packages, security_only: securityOnly },
      })
      .json<PackageRun>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
