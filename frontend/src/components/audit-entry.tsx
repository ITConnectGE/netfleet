"use client";

import { fullWhen } from "@/components/pager";
import type { AuditLogEntry, AuditOutcome } from "@/lib/audit";

export function EntryDetails({ entry: e }: { entry: AuditLogEntry }) {
  return (
    <div className="grid gap-x-6 md:grid-cols-2">
      <Detail label="When">
        <span className="font-mono text-xs">{fullWhen(e.ts)}</span>
      </Detail>
      <Detail label="Source IP">
        <span className="font-mono text-xs">{e.ip_address ?? "—"}</span>
      </Detail>
      <Detail label="User">
        <span className="text-xs">{e.user_email ?? "—"}</span>
      </Detail>
      <Detail label="User agent">
        <span className="font-mono text-xs">{e.user_agent ?? "—"}</span>
      </Detail>
      {e.device_id && (
        <Detail label="Device">
          <span className="font-mono text-xs">
            {e.device_name ? `${e.device_name} · ` : ""}
            {e.device_id}
          </span>
        </Detail>
      )}
      {e.site_id && (
        <Detail label="Site">
          <span className="font-mono text-xs">
            {e.site_name ? `${e.site_name} · ` : ""}
            {e.site_id}
          </span>
        </Detail>
      )}
      {e.request_payload && (
        <Detail label="Request" wide>
          <pre className="mt-1 overflow-x-auto rounded-md bg-background p-2 font-mono text-xs">
            {JSON.stringify(e.request_payload, null, 2)}
          </pre>
        </Detail>
      )}
      {e.response_meta && (
        <Detail label="Response" wide>
          <pre className="mt-1 overflow-x-auto rounded-md bg-background p-2 font-mono text-xs">
            {JSON.stringify(e.response_meta, null, 2)}
          </pre>
        </Detail>
      )}
      {e.error_message && (
        <Detail label="Error" wide>
          <span className="font-mono text-xs text-destructive">{e.error_message}</span>
        </Detail>
      )}
    </div>
  );
}

export function OutcomePill({ outcome }: { outcome: AuditOutcome }) {
  const [cls, label] =
    outcome === "ok"
      ? ["bg-emerald-100 text-emerald-800", "success"]
      : outcome === "denied"
        ? ["bg-amber-100 text-amber-800", "denied"]
        : ["bg-red-100 text-red-800", "error"];
  return (
    <span className={`inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${cls}`}>
      {label}
    </span>
  );
}

function Detail({
  label,
  children,
  wide = false,
}: {
  label: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className={`py-1 ${wide ? "md:col-span-2" : ""}`}>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-0.5">{children}</div>
    </div>
  );
}
