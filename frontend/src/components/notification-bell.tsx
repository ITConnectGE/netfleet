"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  fetchNotifications,
  markNotificationsRead,
  type NotificationFeed,
  type NotificationItem,
} from "@/lib/notifications";

const POLL_INTERVAL_MS = 60_000;

export function NotificationBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const { data } = useQuery<NotificationFeed>({
    queryKey: ["notifications"],
    queryFn: fetchNotifications,
    refetchInterval: POLL_INTERVAL_MS,
    refetchOnWindowFocus: true,
  });

  const markRead = useMutation({
    mutationFn: markNotificationsRead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  // Close on outside click and Escape — the popover sits in the header
  // so it would otherwise stick around when the user nav-clicks.
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle() {
    const next = !open;
    setOpen(next);
    // Only mark as read on open, so the badge actually changes after
    // the user has glanced at the dropdown.
    if (next && data && data.unread_count > 0) {
      markRead.mutate();
    }
  }

  const unread = data?.unread_count ?? 0;
  const items = data?.items ?? [];

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={toggle}
        aria-label={
          unread > 0 ? `${unread} unread notifications` : "Notifications"
        }
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-input bg-background transition hover:bg-accent"
      >
        <BellIcon className="size-4" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 inline-flex min-w-[1.1rem] items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-destructive-foreground">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-3 py-2 text-xs">
            <span className="font-medium">Notifications</span>
            <span className="text-muted-foreground">
              {unread > 0 ? `${unread} new` : "all caught up"}
            </span>
          </div>
          <ul className="max-h-96 overflow-y-auto bg-white">
            {items.length === 0 && (
              <li className="px-3 py-6 text-center text-xs text-muted-foreground">
                Nothing yet.
              </li>
            )}
            {items.map((item) => (
              <Row key={item.id} item={item} onNavigate={() => setOpen(false)} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Row({
  item,
  onNavigate,
}: {
  item: NotificationItem;
  onNavigate: () => void;
}) {
  return (
    <li className="border-t border-border first:border-t-0">
      <Link
        href={item.link_path}
        onClick={onNavigate}
        className={
          item.unread
            ? "flex items-start gap-2 bg-sky-50/70 px-3 py-2 hover:bg-sky-100/80"
            : "flex items-start gap-2 px-3 py-2 hover:bg-accent"
        }
      >
        <span
          className={
            item.unread
              ? "mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full bg-sky-500 ring-2 ring-sky-200"
              : "mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full bg-transparent"
          }
          aria-label={item.unread ? "Unread" : undefined}
        />
        <div className="min-w-0 flex-1">
          <div
            className={`truncate text-xs ${item.unread ? "font-semibold text-foreground" : "font-medium"}`}
          >
            {item.title}
          </div>
          {item.subtitle && (
            <div className="truncate text-[11px] text-muted-foreground">
              {item.subtitle}
            </div>
          )}
          <div className="mt-0.5 text-[10px] text-muted-foreground">
            {formatRelative(item.timestamp)}
          </div>
        </div>
      </Link>
    </li>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function BellIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}
