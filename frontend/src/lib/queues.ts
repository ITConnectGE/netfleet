import { api, readErrorMessage } from "@/lib/api";

export interface SimpleQueue {
  id: string | null;
  name: string;
  target: string | null;
  max_limit: string | null;
  burst_limit: string | null;
  burst_threshold: string | null;
  burst_time: string | null;
  parent: string | null;
  priority: string | null;
  bytes_in: number | null;
  bytes_out: number | null;
  disabled: boolean;
  comment: string | null;
}

export interface SimpleQueueCreate {
  name: string;
  target?: string | null;
  max_limit?: string | null;
  burst_limit?: string | null;
  burst_threshold?: string | null;
  burst_time?: string | null;
  parent?: string | null;
  priority?: string | null;
  disabled?: boolean;
  comment?: string | null;
}

export async function listSimpleQueues(deviceId: string): Promise<SimpleQueue[]> {
  return api.get(`devices/${deviceId}/queues/simple`).json<SimpleQueue[]>();
}

export async function createSimpleQueue(
  deviceId: string,
  payload: SimpleQueueCreate,
): Promise<{ id: string }> {
  try {
    return await api
      .post(`devices/${deviceId}/queues/simple`, { json: payload })
      .json<{ id: string }>();
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function deleteSimpleQueue(deviceId: string, queueId: string): Promise<void> {
  try {
    await api.delete(`devices/${deviceId}/queues/simple/${encodeURIComponent(queueId)}`);
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}

export async function resetSimpleQueueCounters(
  deviceId: string,
  queueId: string,
): Promise<void> {
  try {
    await api.post(
      `devices/${deviceId}/queues/simple/${encodeURIComponent(queueId)}/reset-counters`,
    );
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
