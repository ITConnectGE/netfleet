"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { LogoMark } from "@/components/logo";
import { NotificationBell } from "@/components/notification-bell";
import { ToastProvider } from "@/components/toast";
import { UpdateBanner } from "@/components/update-banner";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fetchMe, logout, type UserPublic } from "@/lib/auth";

interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
}

const NAV = [
  { href: "/dashboard", label: "Overview" },
  // Tenants + Sites + Devices used to be three top-level links; the
  // Fleet page now shows the full hierarchy on one screen, so we keep
  // only that. The per-resource detail pages remain reachable from
  // Fleet links and via direct URL.
  { href: "/dashboard/fleet", label: "Fleet" },
  { href: "/dashboard/bulk", label: "Bulk" },
  { href: "/dashboard/users", label: "Users" },
  // Roles lived here in Phases 1-6; P21 Stage 2 moved them under
  // Settings → Access control to clean up the top bar.
  { href: "/dashboard/events", label: "Events" },
  { href: "/dashboard/audit", label: "Audit log" },
  { href: "/dashboard/reports", label: "Reports" },
  { href: "/dashboard/settings", label: "Settings" },
] as const;

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: me, isLoading } = useQuery<UserPublic | null>({
    queryKey: ["me"],
    queryFn: fetchMe,
    retry: false,
  });
  const { data: health } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => api.get("health").json<HealthResponse>(),
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    if (!isLoading && me === null) {
      router.replace("/login");
    }
  }, [isLoading, me, router]);

  // Force first-login password change. The Profile page detects the
  // same flag and locks itself into the password card until the
  // change-password call succeeds.
  useEffect(() => {
    if (me?.must_change_password && pathname !== "/dashboard/profile") {
      router.replace("/dashboard/profile?force=password");
    }
  }, [me?.must_change_password, pathname, router]);

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }
  if (!me) return null;
  const passwordChangeRequired = me.must_change_password;

  return (
    <ToastProvider>
    <div className="min-h-screen bg-background">
      <UpdateBanner />
      <header className="border-b border-border bg-card">
        <div className="container flex h-14 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link href="/dashboard" className="flex items-center gap-2">
              <LogoMark size={24} />
              <span className="text-base font-semibold tracking-tight">NetFleet</span>
              <span
                className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                title={health ? `running ${health.version}` : ""}
              >
                {health ? `v${health.version}` : "…"}
              </span>
            </Link>
            <nav className="flex items-center gap-1">
              {NAV.map((item) => {
                const active =
                  item.href === "/dashboard"
                    ? pathname === "/dashboard"
                    : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={passwordChangeRequired ? "#" : item.href}
                    onClick={(e) => {
                      if (passwordChangeRequired) e.preventDefault();
                    }}
                    aria-disabled={passwordChangeRequired ? "true" : undefined}
                    title={
                      passwordChangeRequired
                        ? "Change your password first"
                        : undefined
                    }
                    className={cn(
                      "rounded-md px-3 py-1.5 text-sm font-medium transition",
                      active
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                      passwordChangeRequired && "pointer-events-none opacity-50",
                    )}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <NotificationBell />
            <Link
              href="/dashboard/profile"
              title="Open profile"
              className="rounded-md px-2 py-1 text-right text-xs transition hover:bg-accent"
            >
              <div className="font-medium">{me.display_name ?? me.email}</div>
              <div className="text-muted-foreground">{me.is_admin ? "Admin" : "Member"}</div>
            </Link>
            <button
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium transition hover:bg-accent"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="container py-8">{children}</main>
    </div>
    </ToastProvider>
  );
}
