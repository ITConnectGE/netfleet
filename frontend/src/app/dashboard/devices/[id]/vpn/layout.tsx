"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export default function VpnLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  const base = `/dashboard/devices/${params.id}/vpn`;

  const tabs = [
    { href: base, label: "PPP secrets", match: (p: string) => p === base },
    {
      href: `${base}/wireguard`,
      label: "WireGuard",
      match: (p: string) => p.startsWith(`${base}/wireguard`),
    },
    // IPSec → Phase 6c.5
  ] as const;

  return (
    <div>
      <div className="mb-4 inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
        {tabs.map((t) => {
          const active = t.match(pathname);
          return (
            <Link
              key={t.href}
              href={t.href}
              className={cn(
                "rounded px-3 py-1.5 font-medium transition",
                active
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </Link>
          );
        })}
      </div>
      {children}
    </div>
  );
}
