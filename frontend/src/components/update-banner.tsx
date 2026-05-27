"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { getUpdateStatus, isInProgress, type UpdateStatus } from "@/lib/updates";

/**
 * Sits in the dashboard layout — shows when:
 *  - a newer release exists (offer "Update now")
 *  - an update is currently running (live progress link)
 *  - the last update failed (link to logs)
 *
 * Hides itself on the /dashboard/settings/updates page so it doesn't double up.
 */
export function UpdateBanner() {
  const pathname = usePathname();
  const onUpdatesPage = pathname?.startsWith("/dashboard/settings/updates");

  const { data } = useQuery<UpdateStatus>({
    queryKey: ["update-status"],
    queryFn: getUpdateStatus,
    refetchInterval: (q) => (q.state.data && isInProgress(q.state.data.state) ? 2000 : 60_000),
    // The updater may be unreachable on a fresh install — fail silently
    retry: false,
  });

  if (!data || onUpdatesPage) return null;

  if (isInProgress(data.state)) {
    return (
      <Banner color="sky">
        <span>
          Updating to <strong className="font-mono">{data.target_version}</strong> —{" "}
          {data.state.replace("_", " ")}…
        </span>
        <Link href="/dashboard/settings/updates" className="ml-3 underline">
          See progress
        </Link>
      </Banner>
    );
  }

  if (data.state === "failed") {
    return (
      <Banner color="red">
        <span>
          Last update attempt failed.{" "}
          {data.last_error && (
            <span className="opacity-80">({data.last_error})</span>
          )}
        </span>
        <Link href="/dashboard/settings/updates" className="ml-3 underline">
          Review
        </Link>
      </Banner>
    );
  }

  if (data.available) {
    return (
      <Banner color="amber">
        <span>
          NetFleet <strong className="font-mono">{data.available}</strong> is available
          (running <span className="font-mono">{data.current}</span>).
        </span>
        <Link
          href="/dashboard/settings/updates"
          className="ml-3 rounded-md bg-amber-900 px-2 py-0.5 text-xs font-medium text-amber-50 hover:opacity-90"
        >
          Update now
        </Link>
      </Banner>
    );
  }

  return null;
}

function Banner({
  color,
  children,
}: {
  color: "sky" | "amber" | "red";
  children: React.ReactNode;
}) {
  const cls = {
    sky: "border-sky-300 bg-sky-50 text-sky-900",
    amber: "border-amber-300 bg-amber-50 text-amber-900",
    red: "border-red-300 bg-red-50 text-red-900",
  }[color];
  return (
    <div
      className={`flex items-center justify-center border-b px-4 py-2 text-sm ${cls}`}
    >
      {children}
    </div>
  );
}
