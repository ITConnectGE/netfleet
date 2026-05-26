import type { DeviceStatus } from "@/lib/devices";

export function StatusPill({ status }: { status: DeviceStatus }) {
  const cls =
    status === "online"
      ? "bg-emerald-100 text-emerald-800"
      : status === "offline"
        ? "bg-zinc-100 text-zinc-800"
        : status === "error"
          ? "bg-red-100 text-red-800"
          : "bg-amber-100 text-amber-800";
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}
