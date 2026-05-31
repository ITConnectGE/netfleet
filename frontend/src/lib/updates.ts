import { api, readErrorMessage } from "@/lib/api";

export type UpdateState =
  | "idle"
  | "checking"
  | "backing_up"
  | "pulling"
  | "recreating"
  | "health_checking"
  | "success"
  | "failed";

export interface UpdateStatus {
  current: string;
  available: string | null;
  target_version: string | null;
  channel: string;
  repo: string;
  state: UpdateState;
  last_checked_iso: string | null;
  last_error: string | null;
  started_at_iso: string | null;
  finished_at_iso: string | null;
  log_tail: string[];
}

export const IN_PROGRESS_STATES: UpdateState[] = [
  "backing_up",
  "pulling",
  "recreating",
  "health_checking",
];

export function isInProgress(s: UpdateState): boolean {
  return IN_PROGRESS_STATES.includes(s);
}

export async function getUpdateStatus(force = false): Promise<UpdateStatus> {
  return api
    .get("system/update/status", {
      searchParams: force ? { force: "true" } : undefined,
      // Force checks go through the list-mode path on GitHub and so can
      // take a few seconds; widen the timeout vs the default poll.
      timeout: force ? 30_000 : 15_000,
    })
    .json<UpdateStatus>();
}

export async function triggerUpdate(
  version: string,
  backup = true,
): Promise<{ status: string; target_version: string }> {
  try {
    return await api
      .post("system/update", { json: { version, backup }, timeout: 30_000 })
      .json<{ status: string; target_version: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
