"use client";

import { useState } from "react";

import type { DeviceStatus } from "@/lib/devices";
import { formatAbsolute, formatRelative } from "@/lib/time";

const STATUS_LABEL: Record<DeviceStatus, string> = {
  online: "online",
  offline: "offline",
  error: "error",
  unknown: "unknown",
};

/**
 * Status badge with an optional hover tooltip that surfaces the last
 * successful poll time (relative + absolute) and, for `error` status,
 * the captured driver error message. When neither `lastSeenAt` nor
 * `error` is provided we render a plain pill — keeps the dozen-or-so
 * other call sites that don't have this data unchanged.
 */
export function StatusPill({
  status,
  lastSeenAt,
  error,
}: {
  status: DeviceStatus;
  lastSeenAt?: string | null;
  error?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const cls =
    status === "online"
      ? "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200/70"
      : status === "offline"
        ? "bg-zinc-100 text-zinc-700 ring-1 ring-zinc-200"
        : status === "error"
          ? "bg-red-100 text-red-800 ring-1 ring-red-200"
          : "bg-amber-100 text-amber-800 ring-1 ring-amber-200";
  const dotCls =
    status === "online"
      ? "bg-emerald-500"
      : status === "offline"
        ? "bg-zinc-400"
        : status === "error"
          ? "bg-red-500"
          : "bg-amber-500";

  const hasTooltip = Boolean(lastSeenAt) || Boolean(error);
  const seenAbs = formatAbsolute(lastSeenAt);
  const seenRel = formatRelative(lastSeenAt);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => hasTooltip && setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => hasTooltip && setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span
        tabIndex={hasTooltip ? 0 : -1}
        aria-describedby={open ? "status-pill-tooltip" : undefined}
        className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ${cls} ${
          hasTooltip ? "cursor-help" : ""
        }`}
      >
        <span
          className={`inline-block size-1.5 rounded-full ${dotCls} ${
            status === "online" ? "animate-pulse" : ""
          }`}
        />
        {STATUS_LABEL[status]}
      </span>
      {open && hasTooltip && (
        <span
          id="status-pill-tooltip"
          role="tooltip"
          className="absolute right-0 top-full z-30 mt-1 w-64 rounded-md border border-border bg-popover px-3 py-2 text-left text-[11px] leading-snug text-popover-foreground shadow-md"
        >
          <span className="block font-medium text-foreground">
            {status === "online"
              ? "Last polled"
              : status === "error"
                ? "Last attempt"
                : "Last seen"}
          </span>
          <span className="mt-0.5 block">{seenRel}</span>
          <span className="block text-muted-foreground">{seenAbs}</span>
          {error && (
            <span className="mt-1.5 block break-words border-t border-border pt-1.5 text-red-700 dark:text-red-300">
              {error}
            </span>
          )}
        </span>
      )}
    </span>
  );
}
