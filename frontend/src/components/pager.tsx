"use client";

import { useState } from "react";

/** Page numbers to show around `current`: first, last, a window of
 *  neighbours, and `null` for each gap. Always 1-based. */
export function pageWindow(current: number, pages: number, radius = 1): (number | null)[] {
  const keep = new Set<number>([1, pages]);
  for (let p = current - radius; p <= current + radius; p++) {
    if (p >= 1 && p <= pages) keep.add(p);
  }
  // Show a lone page instead of a gap that hides just one number.
  const sorted = [...keep].sort((a, b) => a - b);
  const out: (number | null)[] = [];
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0) {
      const gap = sorted[i] - sorted[i - 1];
      if (gap === 2) out.push(sorted[i] - 1);
      else if (gap > 2) out.push(null);
    }
    out.push(sorted[i]);
  }
  return out;
}

const BTN =
  "inline-flex h-7 min-w-7 items-center justify-center rounded-md border border-input bg-background px-2 text-xs font-medium transition hover:bg-accent disabled:pointer-events-none disabled:opacity-40";
const BTN_ACTIVE =
  "inline-flex h-7 min-w-7 items-center justify-center rounded-md border border-primary bg-primary px-2 text-xs font-semibold text-primary-foreground";

export function Pager({
  offset,
  limit,
  total,
  onOffset,
  onLimit,
  limits = [25, 50, 100, 200],
  noun = "entries",
}: {
  offset: number;
  limit: number;
  total: number;
  onOffset: (offset: number) => void;
  onLimit?: (limit: number) => void;
  limits?: number[];
  noun?: string;
}) {
  const pages = Math.max(1, Math.ceil(total / limit));
  const current = Math.min(Math.floor(offset / limit) + 1, pages);
  const go = (page: number) => onOffset((Math.min(Math.max(page, 1), pages) - 1) * limit);
  const [draft, setDraft] = useState<string | null>(null);
  const atFirst = current <= 1;
  const atLast = current >= pages;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <span>
          {total === 0
            ? `0 ${noun}`
            : `Showing ${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()}`}
        </span>
        {onLimit && (
          <label className="flex items-center gap-1">
            · Rows
            <select
              aria-label="Rows per page"
              value={limit}
              onChange={(e) => onLimit(Number(e.target.value))}
              className="rounded-md border border-input bg-background px-1.5 py-0.5 text-xs text-foreground"
            >
              {limits.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <nav aria-label="Pagination" className="flex flex-wrap items-center gap-1">
        <button type="button" aria-label="First page" disabled={atFirst} onClick={() => go(1)} className={BTN}>
          «
        </button>
        <button
          type="button"
          aria-label="Previous page"
          disabled={atFirst}
          onClick={() => go(current - 1)}
          className={BTN}
        >
          ‹
        </button>
        {pageWindow(current, pages).map((p, i) =>
          p === null ? (
            <span key={`gap-${i}`} aria-hidden="true" className="px-1">
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              aria-label={`Page ${p}`}
              aria-current={p === current ? "page" : undefined}
              onClick={() => go(p)}
              className={p === current ? BTN_ACTIVE : BTN}
            >
              {p}
            </button>
          ),
        )}
        <button
          type="button"
          aria-label="Next page"
          disabled={atLast}
          onClick={() => go(current + 1)}
          className={BTN}
        >
          ›
        </button>
        <button type="button" aria-label="Last page" disabled={atLast} onClick={() => go(pages)} className={BTN}>
          »
        </button>
        <form
          className="ml-2 flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            const n = Number.parseInt(draft ?? "", 10);
            if (Number.isFinite(n)) go(n);
            setDraft(null);
          }}
        >
          <label htmlFor="pager-goto">Go to</label>
          <input
            id="pager-goto"
            inputMode="numeric"
            value={draft ?? String(current)}
            onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, ""))}
            onBlur={() => setDraft(null)}
            className="h-7 w-12 rounded-md border border-input bg-background px-1.5 text-center text-xs text-foreground"
          />
        </form>
      </nav>
    </div>
  );
}

/** Start of a time range, as an ISO string, or undefined for all time. */
export function rangeStart(range: string): string | undefined {
  const hours: Record<string, number> = { "1h": 1, "24h": 24, "7d": 24 * 7, "30d": 24 * 30 };
  const h = hours[range];
  return h ? new Date(Date.now() - h * 3600_000).toISOString() : undefined;
}

export const TIME_RANGES = [
  { value: "1h", label: "Last hour" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "all", label: "All time" },
];

/** "Today 05:41", "Yesterday 23:47", or "3 Nov 14:02" — short enough for a
 *  compact table column; the full timestamp belongs in a tooltip. */
export function shortWhen(iso: string, now = new Date()): string {
  const d = new Date(iso);
  const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86_400_000);
  if (diff === 0) return `Today ${hm}`;
  if (diff === 1) return `Yesterday ${hm}`;
  const sameYear = d.getFullYear() === now.getFullYear();
  const date = d.toLocaleDateString([], {
    day: "numeric",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
  });
  return `${date} ${hm}`;
}

/** Full local timestamp, for tooltips: 2026-11-04 05:41:12 */
export function fullWhen(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
