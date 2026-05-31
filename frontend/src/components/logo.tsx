// Inline SVG logo for NetFleet. Two pieces:
// - `LogoMark` is the just-the-symbol variant (square; great for tab icons,
//   nav corners, social previews).
// - `Logo` pairs the mark with the wordmark and is what we use on auth
//   pages and the landing screen.
//
// The mark is a central node connected to four satellites — the "fleet"
// metaphor for the NetFleet brand. Colours use Tailwind's emerald/slate
// palette so it stays legible on both light and dark backgrounds.

import { cn } from "@/lib/utils";

export function LogoMark({
  size = 32,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label="NetFleet logo mark"
    >
      <rect width="64" height="64" rx="14" fill="#0f172a" />
      <g stroke="#34d399" strokeWidth={3} strokeLinecap="round">
        <line x1="32" y1="32" x2="16" y2="16" />
        <line x1="32" y1="32" x2="48" y2="16" />
        <line x1="32" y1="32" x2="16" y2="48" />
        <line x1="32" y1="32" x2="48" y2="48" />
      </g>
      <circle cx="32" cy="32" r="6" fill="#22c55e" />
      <circle cx="16" cy="16" r="4" fill="#a7f3d0" />
      <circle cx="48" cy="16" r="4" fill="#a7f3d0" />
      <circle cx="16" cy="48" r="4" fill="#a7f3d0" />
      <circle cx="48" cy="48" r="4" fill="#a7f3d0" />
    </svg>
  );
}

export function Logo({
  size = 32,
  className,
  showWordmark = true,
}: {
  size?: number;
  className?: string;
  showWordmark?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark size={size} />
      {showWordmark && (
        <span className="text-lg font-semibold tracking-tight text-foreground">
          NetFleet
        </span>
      )}
    </span>
  );
}
