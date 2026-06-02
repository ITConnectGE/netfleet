"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useEffect, useState, type ReactNode } from "react";

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

// Top-bar nav, grouped semantically so the eye can chunk operations vs.
// monitoring vs. config without reading every label. A thin vertical
// rule renders between groups in `NavBar` below.
const NAV_GROUPS = [
  [
    { href: "/dashboard", label: "Overview" },
    { href: "/dashboard/fleet", label: "Fleet" },
    { href: "/dashboard/bulk", label: "Bulk" },
  ],
  [
    { href: "/dashboard/users", label: "Users" },
    { href: "/dashboard/access-requests", label: "Access requests" },
  ],
  [
    { href: "/dashboard/events", label: "Events" },
    { href: "/dashboard/audit", label: "Audit log" },
    { href: "/dashboard/reports", label: "Reports" },
    { href: "/dashboard/system-health", label: "Host health" },
  ],
  [{ href: "/dashboard/settings", label: "Settings" }],
] as const;

const NAV_FLAT = NAV_GROUPS.flat();

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
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

  // Close the mobile drawer on every route change so the next page isn't
  // covered by the open overlay.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  if (isLoading) {
    return <ShellSkeleton />;
  }
  if (!me) return null;
  const passwordChangeRequired = me.must_change_password;

  return (
    <ToastProvider>
      <div className="min-h-screen bg-background">
        <UpdateBanner />
        <header className="sticky top-0 z-40 border-b border-border bg-card/90 backdrop-blur supports-[backdrop-filter]:bg-card/75">
          <div className="container flex h-14 items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-4 lg:gap-6">
              <Link href="/dashboard" className="flex items-center gap-2" aria-label="NetFleet dashboard">
                <LogoMark size={24} />
                <span className="text-base font-semibold tracking-tight">NetFleet</span>
                <span
                  aria-label={health ? `Running version ${health.version}` : "Loading version"}
                  className="hidden rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground sm:inline"
                >
                  {health ? `v${health.version}` : "…"}
                </span>
              </Link>
              <NavBar
                pathname={pathname}
                passwordChangeRequired={passwordChangeRequired}
              />
            </div>
            <div className="flex shrink-0 items-center gap-2 lg:gap-3">
              <NotificationBell />
              <Link
                href="/dashboard/profile"
                title="Open profile"
                className="hidden max-w-[200px] rounded-md px-2 py-1 text-right text-sm transition hover:bg-accent sm:block"
              >
                <div className="truncate font-medium leading-tight">
                  {me.display_name ?? me.email}
                </div>
                <div className="text-xs leading-tight text-muted-foreground">
                  {me.is_admin ? "Admin" : "Member"}
                </div>
              </Link>
              <button
                onClick={async () => {
                  await logout();
                  router.replace("/login");
                }}
                className="hidden rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium transition hover:bg-accent sm:inline-flex"
              >
                Sign out
              </button>
              <button
                type="button"
                onClick={() => setMobileOpen((v) => !v)}
                aria-label={mobileOpen ? "Close menu" : "Open menu"}
                aria-expanded={mobileOpen}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-input bg-background lg:hidden"
              >
                {mobileOpen ? <CloseIcon /> : <MenuIcon />}
              </button>
            </div>
          </div>
          {mobileOpen && (
            <MobileDrawer
              pathname={pathname}
              me={me}
              passwordChangeRequired={passwordChangeRequired}
              onLogout={async () => {
                await logout();
                router.replace("/login");
              }}
              version={health?.version}
            />
          )}
        </header>
        <main className="container py-8">{children}</main>
      </div>
    </ToastProvider>
  );
}

function NavBar({
  pathname,
  passwordChangeRequired,
}: {
  pathname: string;
  passwordChangeRequired: boolean;
}) {
  return (
    <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary">
      {NAV_GROUPS.map((group, gi) => (
        <Fragment key={gi}>
          {gi > 0 && (
            <span aria-hidden="true" className="mx-1 h-4 w-px bg-border" />
          )}
          {group.map((item) => (
            <NavLink
              key={item.href}
              href={item.href}
              label={item.label}
              active={isActive(pathname, item.href)}
              disabled={passwordChangeRequired}
            />
          ))}
        </Fragment>
      ))}
    </nav>
  );
}

function NavLink({
  href,
  label,
  active,
  disabled,
}: {
  href: string;
  label: string;
  active: boolean;
  disabled: boolean;
}) {
  if (disabled) {
    // Render as a non-interactive span instead of an anchor with a fake
    // href + onClick(preventDefault). Screen readers and keyboard users
    // never reach it, which is what we actually mean by "disabled" here.
    return (
      <span
        aria-disabled="true"
        title="Change your password first"
        className="cursor-not-allowed rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground/50"
      >
        {label}
      </span>
    );
  }
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "rounded-md px-3 py-1.5 text-sm font-medium transition",
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
      )}
    >
      {label}
    </Link>
  );
}

function MobileDrawer({
  pathname,
  me,
  passwordChangeRequired,
  onLogout,
  version,
}: {
  pathname: string;
  me: UserPublic;
  passwordChangeRequired: boolean;
  onLogout: () => Promise<void>;
  version: string | undefined;
}) {
  return (
    <div className="border-t border-border bg-card lg:hidden">
      <div className="container py-3">
        <div className="mb-3 flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-sm">
          <div className="min-w-0">
            <div className="truncate font-medium">{me.display_name ?? me.email}</div>
            <div className="text-xs text-muted-foreground">
              {me.is_admin ? "Admin" : "Member"}
              {version ? ` · v${version}` : ""}
            </div>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-xs font-medium hover:bg-accent"
          >
            Sign out
          </button>
        </div>
        <nav aria-label="Primary" className="space-y-3">
          {NAV_GROUPS.map((group, gi) => (
            <div key={gi} className="space-y-1">
              {group.map((item) => {
                const active = isActive(pathname, item.href);
                if (passwordChangeRequired) {
                  return (
                    <span
                      key={item.href}
                      aria-disabled="true"
                      className="block cursor-not-allowed rounded-md px-3 py-2 text-sm font-medium text-muted-foreground/50"
                    >
                      {item.label}
                    </span>
                  );
                }
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "block rounded-md px-3 py-2 text-sm font-medium",
                      active
                        ? "bg-accent text-accent-foreground"
                        : "text-foreground hover:bg-accent",
                    )}
                  >
                    {item.label}
                  </Link>
                );
              })}
              {gi < NAV_GROUPS.length - 1 && <div className="h-px bg-border" />}
            </div>
          ))}
        </nav>
      </div>
    </div>
  );
}

function ShellSkeleton() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card">
        <div className="container flex h-14 items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="size-6 rounded-md bg-muted animate-pulse" />
            <div className="h-4 w-24 rounded bg-muted animate-pulse" />
          </div>
          <div className="h-8 w-32 rounded bg-muted animate-pulse" />
        </div>
      </header>
      <main className="container py-8" aria-busy="true" aria-live="polite">
        <div className="space-y-4">
          <div className="h-6 w-48 rounded bg-muted animate-pulse" />
          <div className="h-4 w-72 rounded bg-muted animate-pulse" />
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="h-32 rounded-lg bg-card border border-border animate-pulse" />
            <div className="h-32 rounded-lg bg-card border border-border animate-pulse" />
          </div>
        </div>
      </main>
    </div>
  );
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  return pathname.startsWith(href);
}

// Used by NAV_FLAT consumers in test/storybook contexts; suppress unused
// warning while preserving the export shape we already had.
void NAV_FLAT;

function MenuIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-4"
      aria-hidden
    >
      <path d="M3 6h18" />
      <path d="M3 12h18" />
      <path d="M3 18h18" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-4"
      aria-hidden
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}
