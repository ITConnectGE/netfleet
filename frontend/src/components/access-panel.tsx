"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import {
  fetchDeviceAccess,
  fetchSiteAccess,
  fetchTenantAccess,
  type AccessEntry,
  type AccessReport,
  type ScopeKind,
} from "@/lib/access";

interface Props {
  scope: Exclude<ScopeKind, "organization">;
  id: string;
}

export function AccessPanel({ scope, id }: Props) {
  const { data, isLoading, error } = useQuery<AccessReport>({
    queryKey: ["access", scope, id],
    queryFn: () =>
      scope === "tenant"
        ? fetchTenantAccess(id)
        : scope === "site"
          ? fetchSiteAccess(id)
          : fetchDeviceAccess(id),
    enabled: Boolean(id),
  });

  return (
    <section className="mt-8 rounded-lg border border-border bg-card p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Who has access here?</h2>
        <span className="text-xs text-muted-foreground">
          {data ? `${data.entries.length} grant${data.entries.length === 1 ? "" : "s"}` : ""}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Direct and inherited assignments. Org-wide roles cover everything; a
        tenant-scope role covers all sites and devices under that tenant; a
        site-scope role covers its devices.
      </p>

      {isLoading && (
        <p className="mt-3 text-sm text-muted-foreground">Loading…</p>
      )}
      {error && (
        <p className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {(error as Error).message}
        </p>
      )}

      {data && data.entries.length === 0 && (
        <p className="mt-3 rounded-md border border-dashed border-border bg-background p-3 text-center text-xs text-muted-foreground">
          Nobody has access yet (other than super-admins).
        </p>
      )}

      {data && data.entries.length > 0 && (
        <div className="mt-3 overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2 font-medium">Granted via</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.entries.map((e, i) => (
                <Row key={`${e.user_id}:${e.role_id ?? "admin"}:${i}`} e={e} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Row({ e }: { e: AccessEntry }) {
  return (
    <tr className="hover:bg-accent/30">
      <td className="px-3 py-2">
        <Link
          href={`/dashboard/users/${e.user_id}`}
          className="font-medium hover:underline"
        >
          {e.display_name ?? e.email}
        </Link>
        <span className="ml-2 text-[11px] text-muted-foreground">{e.email}</span>
      </td>
      <td className="px-3 py-2 text-xs">
        {e.is_admin && e.role_id === null ? (
          <span className="rounded-md bg-primary/10 px-1.5 py-0.5 font-medium text-primary">
            super-admin
          </span>
        ) : (
          e.role_name ?? "—"
        )}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {e.source_scope_type === null ? (
          <span>bypass via super-admin</span>
        ) : (
          <>
            <span className="font-mono">{e.source_scope_type}</span>
            {e.source_scope_label && (
              <span className="ml-1">· {e.source_scope_label}</span>
            )}
          </>
        )}
      </td>
    </tr>
  );
}
