"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { listIpServices, updateIpService, type IpService } from "@/lib/device-ops";

export default function DeviceServicesPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;

  const { data: services, isLoading, error } = useQuery<IpService[]>({
    queryKey: ["device-services", deviceId],
    queryFn: () => listIpServices(deviceId),
  });

  return (
    <div>
      <h2 className="text-lg font-semibold">IP services</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        RouterOS management protocols. Disable anything you don&apos;t need exposed —
        especially the non-TLS variants and Telnet.
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        <strong>Whitelist:</strong> in <code>Allowed from</code>, enter a comma-separated
        list of IPs / subnets (e.g. <code>10.0.0.0/8,192.168.1.5</code>). Leave blank to
        accept connections from anywhere. Click <strong>Save</strong> (or press Enter) to
        apply.
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
              <th className="px-4 py-2.5 font-medium">Allowed from (whitelist)</th>
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
            {services?.map((s) => (
              <ServiceRow key={s.name} deviceId={deviceId} service={s} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ServiceRow({ deviceId, service }: { deviceId: string; service: IpService }) {
  const qc = useQueryClient();

  const insecure =
    service.enabled && !service.tls_only && !["api", "winbox", "ssh"].includes(service.name);

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) => updateIpService(deviceId, service.name, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device-services", deviceId] }),
  });

  const portMut = useMutation({
    mutationFn: (port: number) => updateIpService(deviceId, service.name, { port }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device-services", deviceId] }),
  });

  const addressMut = useMutation({
    mutationFn: (address: string) => updateIpService(deviceId, service.name, { address }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device-services", deviceId] }),
  });

  // Local editor state — kept in sync with server-confirmed values via useEffect.
  const [port, setPort] = useState<string>(String(service.port));
  const [address, setAddress] = useState<string>(service.address ?? "");

  useEffect(() => setPort(String(service.port)), [service.port]);
  useEffect(() => setAddress(service.address ?? ""), [service.address]);

  const portDirty = port !== String(service.port);
  const addressDirty = address.trim() !== (service.address ?? "");

  const portValid = port !== "" && Number(port) >= 1 && Number(port) <= 65535;

  const savePort = () => {
    if (portDirty && portValid) portMut.mutate(Number(port));
  };
  const saveAddress = () => {
    if (addressDirty) addressMut.mutate(address.trim());
  };

  const lastError = (portMut.error ?? addressMut.error ?? toggleMut.error) as
    | Error
    | undefined;

  return (
    <>
      <tr className="hover:bg-accent/30">
        <td className="px-4 py-3 font-mono">
          {service.name}
          {insecure && (
            <span className="ml-2 rounded-md bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
              consider disabling
            </span>
          )}
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            <input
              type="number"
              min={1}
              max={65535}
              value={port}
              onChange={(e) => setPort(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  savePort();
                }
              }}
              className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {portDirty && (
              <button
                type="button"
                onClick={savePort}
                disabled={!portValid || portMut.isPending}
                className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {portMut.isPending ? "…" : "Save"}
              </button>
            )}
          </div>
        </td>
        <td className="px-4 py-3 text-xs">
          {service.tls_only ? (
            <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-emerald-800">
              TLS
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              value={address}
              placeholder="any"
              onChange={(e) => setAddress(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  saveAddress();
                }
              }}
              className="w-56 rounded-md border border-input bg-background px-2 py-1 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {addressDirty && (
              <button
                type="button"
                onClick={saveAddress}
                disabled={addressMut.isPending}
                className="rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {addressMut.isPending ? "…" : "Save"}
              </button>
            )}
          </div>
        </td>
        <td className="px-4 py-3 text-right">
          <button
            onClick={() => toggleMut.mutate(!service.enabled)}
            disabled={toggleMut.isPending}
            className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium transition ${
              service.enabled
                ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-200"
                : "bg-zinc-100 text-zinc-800 hover:bg-zinc-200"
            }`}
          >
            <span
              className={`size-2 rounded-full ${service.enabled ? "bg-emerald-500" : "bg-zinc-400"}`}
            />
            {service.enabled ? "enabled" : "disabled"}
          </button>
        </td>
      </tr>
      {lastError && (
        <tr>
          <td colSpan={5} className="px-4 pb-2 text-xs text-destructive">
            {lastError.message}
          </td>
        </tr>
      )}
    </>
  );
}
