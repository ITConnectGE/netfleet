"use client";

import { useQuery } from "@tanstack/react-query";

import {
  getInterfaceConfigs,
  methodLabel,
  type InterfaceConfig,
} from "@/lib/linux";
import { formatBytes } from "@/lib/resources";
import { cn } from "@/lib/utils";

/**
 * One row per interface, everything about its addressing together.
 *
 * The RouterOS Network tab splits addresses, routes and interfaces across
 * separate tables because that is how RouterOS stores them. A Linux
 * operator asking "what is eth0 doing" wants address, whether it was
 * leased or configured, mask, gateway and resolvers in one place.
 */
export function LinuxAddresses({ deviceId }: { deviceId: string }) {
  const { data, isLoading, error, refetch, isFetching } = useQuery<
    InterfaceConfig[]
  >({
    queryKey: ["interface-configs", deviceId],
    queryFn: () => getInterfaceConfigs(deviceId),
    enabled: Boolean(deviceId),
  });

  return (
    <section className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Addressing per interface, read live from the host.
        </p>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="shrink-0 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          {isFetching ? "Reading…" : "Refresh"}
        </button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Reading…</p>}
      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </p>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {data?.map((i) => (
          <div key={i.name} className="rounded-lg border border-border bg-card p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "inline-block size-2 rounded-full",
                    i.state === "UP"
                      ? "bg-emerald-500"
                      : i.state === "DOWN"
                        ? "bg-zinc-400"
                        : "bg-amber-500",
                  )}
                  title={i.state ?? "unknown"}
                />
                <span className="font-mono text-sm font-semibold">{i.name}</span>
                {i.vlan_id != null && (
                  <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-900">
                    VLAN {i.vlan_id} on {i.vlan_parent}
                  </span>
                )}
              </div>
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-medium",
                  i.method === "dhcp"
                    ? "bg-sky-100 text-sky-900"
                    : i.method === "static"
                      ? "bg-violet-100 text-violet-900"
                      : "bg-zinc-100 text-zinc-700",
                )}
              >
                {methodLabel(i.method)}
              </span>
            </div>

            <dl className="mt-3 space-y-1 text-xs">
              <Row label="Address">
                {i.addresses.length ? (
                  <span className="font-mono">{i.addresses.join(", ")}</span>
                ) : (
                  "—"
                )}
              </Row>
              <Row label="Netmask">
                <span className="font-mono">{i.netmask ?? "—"}</span>
              </Row>
              <Row label="Gateway">
                <span className="font-mono">{i.gateway ?? "—"}</span>
              </Row>
              <Row label="DNS">
                <span className="font-mono">
                  {i.dns_servers.length ? i.dns_servers.join(", ") : "—"}
                </span>
              </Row>
              {i.dns_search.length > 0 && (
                <Row label="Search">
                  <span className="font-mono">{i.dns_search.join(", ")}</span>
                </Row>
              )}
              {i.method === "dhcp" && (
                <Row label="DHCP server">
                  <span className="font-mono">{i.dhcp_server ?? "unknown"}</span>
                </Row>
              )}
              <Row label="MAC">
                <span className="font-mono">{i.mac_address ?? "—"}</span>
              </Row>
              <Row label="MTU">{i.mtu ?? "—"}</Row>
              <Row label="Traffic">
                <span className="font-mono">
                  ↓ {formatBytes(i.rx_bytes)} · ↑ {formatBytes(i.tx_bytes)}
                </span>
              </Row>
              {/* Worth showing even though nothing writes yet: an address
                  changed behind the owning subsystem's back gets silently
                  reverted at the next renew or reboot. */}
              <Row label="Managed by">{i.managed_by ?? "not managed"}</Row>
            </dl>
          </div>
        ))}
      </div>

      {data && data.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Editing addresses — switching between DHCP and static, release and
          renew, VLAN tagging — is not enabled yet. Those changes can cut the
          connection NetFleet manages the host over, so they are landing
          together with an automatic rollback that restores the previous
          configuration if the host does not come back.
        </p>
      )}
    </section>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <dt className="w-24 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-all">{children}</dd>
    </div>
  );
}
