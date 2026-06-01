/**
 * Human-friendly relative time ("5m ago", "3h ago") plus a one-shot
 * absolute formatter for tooltips and audit rows. Keep the breakpoints
 * coarse — operators glancing at the fleet table don't need second
 * precision; an exact ISO timestamp lives in the tooltip.
 */

export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const now = Date.now();
  const diff = now - then;
  if (diff < 0) {
    // Server clock ahead of ours by a hair — treat as "just now" so we
    // don't render "-3m ago" on a freshly-polled device.
    return "just now";
  }
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function formatAbsolute(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}
