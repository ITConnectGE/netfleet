import { api, readErrorMessage } from "@/lib/api";

export type NotificationKind = "firmware_update" | "device_added";

export interface NotificationItem {
  id: string;
  kind: NotificationKind;
  title: string;
  subtitle: string | null;
  timestamp: string;
  link_path: string;
  unread: boolean;
}

export interface NotificationFeed {
  unread_count: number;
  items: NotificationItem[];
}

export async function fetchNotifications(): Promise<NotificationFeed> {
  return api.get("notifications").json<NotificationFeed>();
}

export async function markNotificationsRead(): Promise<void> {
  try {
    await api.post("notifications/mark-read");
  } catch (e) {
    throw new Error(await readErrorMessage(e));
  }
}
