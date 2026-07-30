import { cn } from "@/lib/utils";

/**
 * A single horizontal usage meter.
 *
 * Colour is driven by the number, not by the caller: the point of this
 * control is that 91% looks alarming everywhere it appears, without each
 * call site re-deciding where "alarming" starts.
 */
export function UsageBar({
  pct,
  label,
  detail,
  className,
}: {
  pct: number | null | undefined;
  label: string;
  detail?: string;
  className?: string;
}) {
  const value = pct == null ? null : Math.max(0, Math.min(100, pct));
  const tone =
    value == null
      ? "bg-muted-foreground/30"
      : value >= 90
        ? "bg-destructive"
        : value >= 75
          ? "bg-amber-500"
          : "bg-emerald-500";

  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="font-medium text-foreground">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {value == null ? "—" : `${value.toFixed(1)}%`}
        </span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
        role="meter"
        aria-valuenow={value ?? undefined}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div
          className={cn("h-full rounded-full transition-all", tone)}
          style={{ width: `${value ?? 0}%` }}
        />
      </div>
      {detail && (
        <p className="text-[11px] tabular-nums text-muted-foreground">{detail}</p>
      )}
    </div>
  );
}
