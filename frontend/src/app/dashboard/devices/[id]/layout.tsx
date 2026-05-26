"use client";

import Link from "next/link";
import { usePathname, useParams } from "next/navigation";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export default function DeviceLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  const base = `/dashboard/devices/${params.id}`;

  const tabs = [
    { href: base, label: "Overview" },
    { href: `${base}/services`, label: "IP services" },
    { href: `${base}/system-users`, label: "Device users" },
    { href: `${base}/vpn`, label: "VPN" },
    // Backups (Phase 7) will be added when that page ships.
  ] as const;

  return (
    <div>
      <nav className="mb-6 flex gap-1 border-b border-border">
        {tabs.map((t) => {
          const active = pathname === t.href;
          return (
            <Link
              key={t.href}
              href={t.href}
              className={cn(
                "border-b-2 px-3 py-2 text-sm font-medium transition",
                active
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}
