"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { listSites, type Site } from "@/lib/sites";

/**
 * Flat cross-tenant view of every site. Sites are now created from a tenant's
 * detail page (Tenants → pick one → + New site), so this page is read-only.
 */
export default function SitesPage() {
  const { data: sites, isLoading } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: () => listSites(),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">All sites</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Flat list across every tenant. New sites are added from{" "}
        <Link href="/dashboard/tenants" className="text-primary hover:underline">
          Tenants
        </Link>{" "}
        → tenant detail page.
      </p>

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Tenant</th>
              <th className="px-4 py-2.5 font-medium">Site</th>
              <th className="px-4 py-2.5 font-medium">Address</th>
              <th className="px-4 py-2.5 font-medium">Devices</th>
              <th className="px-4 py-2.5 font-medium">Contact</th>
              <th className="px-4 py-2.5 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (!sites || sites.length === 0) && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  No sites yet.
                </td>
              </tr>
            )}
            {sites?.map((s) => (
              <tr key={s.id} className="hover:bg-accent/30">
                <td className="px-4 py-3">
                  <Link
                    href={`/dashboard/tenants/${s.tenant_id}`}
                    className="text-primary hover:underline"
                  >
                    {s.tenant_name ?? "—"}
                  </Link>
                </td>
                <td className="px-4 py-3 font-medium">
                  <Link
                    href={`/dashboard/sites/${s.id}`}
                    className="text-primary hover:underline"
                  >
                    {s.name}
                  </Link>
                  <div className="font-mono text-[10px] text-muted-foreground">
                    {s.slug}
                  </div>
                </td>
                <td className="max-w-xs truncate px-4 py-3 text-xs text-muted-foreground">
                  {s.address ?? "—"}
                </td>
                <td className="px-4 py-3">{s.device_count}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {s.contact_email ?? "—"}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/dashboard/sites/${s.id}`}
                    className="text-xs text-primary hover:underline"
                  >
                    Edit →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
