"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";

import { listIpServices, updateIpService, type IpService } from "@/lib/device-ops";

export default function DeviceServicesPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const qc = useQueryClient();

  const { data: services, isLoading, error } = useQuery<IpService[]>({
    queryKey: ["device-services", deviceId],
    queryFn: () => listIpServices(deviceId),
  });

  const toggleMut = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      updateIpService(deviceId, name, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device-services", deviceId] }),
  });

  const portMut = useMutation({
    mutationFn: ({ name, port }: { name: string; port: number }) =>
      updateIpService(deviceId, name, { port }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device-services", deviceId] }),
  });

  return (
    <div>
      <h2 className="text-lg font-semibold">IP services</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        RouterOS management protocols. Disable anything you don&apos;t need exposed —
        especially the non-TLS variants and Telnet.
      </p>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Service</th>
              <th className="px-4 py-2.5 font-medium">Port</th>
              <th className="px-4 py-2.5 font-medium">TLS</th>
              <th className="px-4 py-2.5 font-medium">Bind address</th>
              <th className="px-4 py-2.5 font-medium text-right">Enabled</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {services?.map((s) => {
              const insecure =
                s.enabled && !s.tls_only && !["api", "winbox", "ssh"].includes(s.name);
              return (
                <tr key={s.name} className="hover:bg-accent/30">
                  <td className="px-4 py-3 font-mono">
                    {s.name}
                    {insecure && (
                      <span className="ml-2 rounded-md bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                        consider disabling
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="number"
                      min={1}
                      max={65535}
                      defaultValue={s.port}
                      onBlur={(e) => {
                        const v = Number(e.target.value);
                        if (v && v !== s.port) portMut.mutate({ name: s.name, port: v });
                      }}
                      className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {s.tls_only ? (
                      <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-emerald-800">
                        TLS
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {s.address ?? "any"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() =>
                        toggleMut.mutate({ name: s.name, enabled: !s.enabled })
                      }
                      disabled={toggleMut.isPending}
                      className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium transition ${
                        s.enabled
                          ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-200"
                          : "bg-zinc-100 text-zinc-800 hover:bg-zinc-200"
                      }`}
                    >
                      <span
                        className={`size-2 rounded-full ${s.enabled ? "bg-emerald-500" : "bg-zinc-400"}`}
                      />
                      {s.enabled ? "enabled" : "disabled"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
