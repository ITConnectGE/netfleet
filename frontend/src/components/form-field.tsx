"use client";

import { useState, type ReactNode } from "react";

/**
 * Shared form-field shell used across the dashboard.
 *
 * Two slots help an operator without crowding the input itself:
 *  - `tooltip` — conceptual help. Rendered as an info-icon next to the
 *    label; hovering or focusing the icon reveals a small popover.
 *    Use this for "why does this field exist / what does it affect."
 *  - `example` — italic micro-text under the input. Use it for format
 *    examples ("e.g. 10.0.0.0/24"). The literal input's `placeholder`
 *    should stay short — typically just the same format example without
 *    any prose.
 *
 * Earlier forms in the dashboard tend to put instructions inside the
 * placeholder. Migrate those over by:
 *   1. moving the prose into `tooltip` if it explains *why*,
 *   2. moving the format hint into `example` (italic note),
 *   3. trimming the `placeholder` to a literal example or removing it.
 */
export function Field({
  label,
  htmlFor,
  tooltip,
  example,
  required,
  error,
  children,
}: {
  label: ReactNode;
  htmlFor?: string;
  tooltip?: ReactNode;
  example?: ReactNode;
  required?: boolean;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <label htmlFor={htmlFor} className="text-sm font-medium">
          {label}
          {required && <span className="ml-0.5 text-destructive">*</span>}
        </label>
        {tooltip && <InfoTooltip>{tooltip}</InfoTooltip>}
      </div>
      {children}
      {example && (
        <p className="text-[11px] italic text-muted-foreground">{example}</p>
      )}
      {error && (
        <p className="text-[11px] text-destructive">{error}</p>
      )}
    </div>
  );
}

export function InfoTooltip({ children }: { children: ReactNode }) {
  // Hover/focus toggle so the popover is reachable by keyboard. We
  // intentionally render the popover inside the same wrapper so it
  // positions relative to the icon without any portal plumbing.
  const [open, setOpen] = useState(false);
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label="More info"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex size-4 items-center justify-center rounded-full border border-border bg-background text-[10px] font-semibold text-muted-foreground transition hover:border-primary/40 hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-5 top-0 z-30 w-64 rounded-md border border-border bg-popover px-3 py-2 text-xs leading-snug text-popover-foreground shadow-md"
        >
          {children}
        </span>
      )}
    </span>
  );
}
