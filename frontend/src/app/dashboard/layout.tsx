"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  HeartPulse,
  Layers,
  LayoutDashboard,
  LogOut,
  type LucideIcon,
  Menu,
  Network,
  ScrollText,
  Settings,
  Siren,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

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

interface NavItemDef {
  href: string;
  label: string;
  icon: LucideIcon;
}

// Left-rail nav, grouped semantically so the eye can chunk operations vs.
// access vs. monitoring vs. config. Each group gets a small section label.
const NAV_GROUPS: { label: string; items: NavItemDef[] }[] = [
  {
    label: "Operations",
    items: [
      { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
      { href: "/dashboard/fleet", label: "Fleet", icon: Network },
      { href: "/dashboard/bulk", label: "Bulk", icon: Layers },
    ],
  },
  {
    label: "Access",
    items: [
      { href: "/dashboard/users", label: "Users", icon: Users },
      { href: "/dashboard/access-requests", label: "Access requests", icon: UserCheck },
    ],
  },
  {
    label: "Monitoring",
    items: [
      { href: "/dashboard/events", label: "Events", icon: Siren },
      { href: "/dashboard/audit", label: "Audit log", icon: ScrollText },
      { href: "/dashboard/reports", label: "Reports", icon: BarChart3 },
      { href: "/dashboard/system-health", label: "Host health", icon: HeartPulse },
    ],
  },
  {
    label: "System",
    items: [{ href: "/dashboard/settings", label: "Settings", icon: Settings }],
  },
];

const SIDEBAR_WIDTH = "w-64";

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
  const onLogout = async () => {
    await logout();
    router.replace("/login");
  };

  return (
    <ToastProvider>
      <div className="min-h-screen bg-background">
        <UpdateBanner />
        <div className="flex">
          {/* Desktop sidebar */}
          <aside
            className={cn(
              "sticky top-0 hidden h-screen shrink-0 border-r border-border bg-card lg:block",
              SIDEBAR_WIDTH,
            )}
          >
            <SidebarContent
              pathname={pathname}
              me={me}
              passwordChangeRequired={passwordChangeRequired}
              onLogout={onLogout}
              version={health?.version}
            />
          </aside>

          {/* Main column */}
          <div className="flex min-h-screen min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-card/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-card/65 sm:px-6 lg:px-10">
              <button
                type="button"
                onClick={() => setMobileOpen(true)}
                aria-label="Open menu"
                className="inline-flex size-9 items-center justify-center rounded-md border border-input bg-background transition hover:bg-accent lg:hidden"
              >
                <Menu className="size-4" />
              </button>
              <Link
                href="/dashboard"
                className="flex items-center gap-2 lg:hidden"
                aria-label="NetFleet dashboard"
              >
                <LogoMark size={22} />
                <span className="text-sm font-semibold tracking-tight">NetFleet</span>
              </Link>
              <div className="ml-auto flex items-center gap-2">
                <NotificationBell />
              </div>
            </header>

            <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-6 lg:px-10">
              {children}
            </main>
          </div>
        </div>

        {/* Mobile drawer */}
        {mobileOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div
              className="absolute inset-0 bg-foreground/40 backdrop-blur-sm animate-in fade-in"
              onClick={() => setMobileOpen(false)}
              aria-hidden
            />
            <div
              className={cn(
                "absolute inset-y-0 left-0 max-w-[85%] border-r border-border bg-card shadow-xl animate-in slide-in-from-left duration-200",
                SIDEBAR_WIDTH,
              )}
            >
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close menu"
                className="absolute right-3 top-3 inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition hover:bg-accent"
              >
                <X className="size-4" />
              </button>
              <SidebarContent
                pathname={pathname}
                me={me}
                passwordChangeRequired={passwordChangeRequired}
                onLogout={onLogout}
                version={health?.version}
                onNavigate={() => setMobileOpen(false)}
              />
            </div>
          </div>
        )}
      </div>
    </ToastProvider>
  );
}

function SidebarContent({
  pathname,
  me,
  passwordChangeRequired,
  onLogout,
  version,
  onNavigate,
}: {
  pathname: string;
  me: UserPublic;
  passwordChangeRequired: boolean;
  onLogout: () => void | Promise<void>;
  version: string | undefined;
  onNavigate?: () => void;
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Brand */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border/70 px-5">
        <Link
          href="/dashboard"
          onClick={onNavigate}
          className="flex items-center gap-2.5"
          aria-label="NetFleet dashboard"
        >
          <LogoMark size={26} />
          <span className="text-[15px] font-semibold tracking-tight">NetFleet</span>
        </Link>
        {version && (
          <span
            aria-label={`Running version ${version}`}
            className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
          >
            v{version}
          </span>
        )}
      </div>

      {/* Nav */}
      <nav aria-label="Primary" className="flex-1 space-y-6 overflow-y-auto px-3 py-5">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="space-y-1">
            <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/60">
              {group.label}
            </div>
            {group.items.map((item) => (
              <NavItem
                key={item.href}
                item={item}
                active={isActive(pathname, item.href)}
                disabled={passwordChangeRequired}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        ))}
      </nav>

      {/* Footer: profile + sign out */}
      <div className="space-y-1 border-t border-border/70 p-3">
        <Link
          href="/dashboard/profile"
          onClick={onNavigate}
          title="Open profile"
          className="flex items-center gap-3 rounded-lg px-2 py-2 transition hover:bg-accent"
        >
          <Avatar name={me.display_name ?? me.email} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium leading-tight">
              {me.display_name ?? me.email}
            </div>
            <div className="text-xs leading-tight text-muted-foreground">
              {me.is_admin ? "Admin" : "Member"}
            </div>
          </div>
        </Link>
        <button
          type="button"
          onClick={onLogout}
          className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
        >
          <LogOut className="size-[18px]" />
          Sign out
        </button>
      </div>
    </div>
  );
}

function NavItem({
  item,
  active,
  disabled,
  onNavigate,
}: {
  item: NavItemDef;
  active: boolean;
  disabled: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  if (disabled) {
    // Non-interactive span rather than a dead anchor: screen readers and
    // keyboard users never reach it, which is what "disabled" means here.
    return (
      <span
        aria-disabled="true"
        title="Change your password first"
        className="flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground/40"
      >
        <Icon className="size-[18px] shrink-0" />
        {item.label}
      </span>
    );
  }
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
        active
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {active && (
        <span
          aria-hidden
          className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-primary"
        />
      )}
      <Icon
        className={cn(
          "size-[18px] shrink-0 transition-colors",
          active ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
        )}
      />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

function Avatar({ name }: { name: string }) {
  const initials =
    name
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((s) => s[0]?.toUpperCase() ?? "")
      .join("") || "?";
  return (
    <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
      {initials}
    </span>
  );
}

function ShellSkeleton() {
  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden h-screen w-64 shrink-0 border-r border-border bg-card lg:block">
        <div className="flex h-14 items-center gap-2.5 border-b border-border/70 px-5">
          <div className="size-6 animate-pulse rounded-md bg-muted" />
          <div className="h-4 w-24 animate-pulse rounded bg-muted" />
        </div>
        <div className="space-y-2 p-5">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-8 w-full animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      </aside>
      <div className="flex min-h-screen flex-1 flex-col">
        <header className="flex h-14 items-center border-b border-border bg-card px-6">
          <div className="ml-auto size-8 animate-pulse rounded-md bg-muted" />
        </header>
        <main
          className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-6 lg:px-10"
          aria-busy="true"
          aria-live="polite"
        >
          <div className="space-y-4">
            <div className="h-6 w-48 animate-pulse rounded bg-muted" />
            <div className="h-4 w-72 animate-pulse rounded bg-muted" />
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="h-32 animate-pulse rounded-lg border border-border bg-card" />
              <div className="h-32 animate-pulse rounded-lg border border-border bg-card" />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  return pathname.startsWith(href);
}
