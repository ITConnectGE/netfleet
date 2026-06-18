"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import {
  bulkZabbixSnmpSetup,
  type BulkResult,
  type BulkZabbixSnmpSetupResponse,
} from "@/lib/bulk";
import { listDevices, type Device } from "@/lib/devices";
import { listSites, type Site } from "@/lib/sites";

type Step = "devices" | "settings" | "apply";

export default function ZabbixSnmpWizardPage() {
  const [step, setStep] = useState<Step>("devices");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Settings carried into the apply step.
  const [zabbixAddrs, setZabbixAddrs] = useState("");
  const [addressList, setAddressList] = useState("zabbix");
  const [community, setCommunity] = useState("public");
  const [snmpPort, setSnmpPort] = useState(161);
  const [configureCommunity, setConfigureCommunity] = useState(true);

  const addrList = useMemo(
    () =>
      zabbixAddrs
        .split(/[,\s]+/)
        .map((a) => a.trim())
        .filter(Boolean),
    [zabbixAddrs],
  );

  return (
    <div>
      <Link
        href="/dashboard/bulk"
        className="text-xs text-muted-foreground hover:underline"
      >
        ← Bulk
      </Link>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">
        SNMP for Zabbix
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Pick MikroTiks, then in one pass NetFleet adds the Zabbix IP to a
        firewall address-list, opens an accept rule for SNMP, points the
        community at Zabbix, and enables SNMP — on every selected device in
        parallel.
      </p>

      <ol className="mt-6 flex flex-wrap gap-1 text-xs">
        {(
          [
            ["devices", "Devices"],
            ["settings", "Settings"],
            ["apply", "Review & apply"],
          ] as [Step, string][]
        ).map(([id, label], i) => {
          const active = id === step;
          const done =
            (id === "devices" && step !== "devices" && selected.size > 0) ||
            (id === "settings" && step === "apply");
          return (
            <li
              key={id}
              className={`flex items-center gap-1 rounded-md px-2.5 py-1 ${
                active
                  ? "bg-primary/10 text-primary"
                  : done
                    ? "bg-muted text-muted-foreground"
                    : "bg-muted/40 text-muted-foreground"
              }`}
            >
              <span className="font-mono">{i + 1}</span> · {label}
              {done && !active && <span>✓</span>}
            </li>
          );
        })}
      </ol>

      <div className="mt-6">
        {step === "devices" && (
          <DevicesStep
            selected={selected}
            setSelected={setSelected}
            onNext={() => setStep("settings")}
          />
        )}
        {step === "settings" && (
          <SettingsStep
            zabbixAddrs={zabbixAddrs}
            setZabbixAddrs={setZabbixAddrs}
            addressList={addressList}
            setAddressList={setAddressList}
            community={community}
            setCommunity={setCommunity}
            snmpPort={snmpPort}
            setSnmpPort={setSnmpPort}
            configureCommunity={configureCommunity}
            setConfigureCommunity={setConfigureCommunity}
            addrCount={addrList.length}
            onBack={() => setStep("devices")}
            onNext={() => setStep("apply")}
          />
        )}
        {step === "apply" && (
          <ApplyStep
            deviceIds={Array.from(selected)}
            zabbixAddresses={addrList}
            addressListName={addressList}
            communityName={community}
            snmpPort={snmpPort}
            configureCommunity={configureCommunity}
            onBack={() => setStep("settings")}
          />
        )}
      </div>
    </div>
  );
}

// ---------------- Step 1: Devices ----------------

function DevicesStep({
  selected,
  setSelected,
  onNext,
}: {
  selected: Set<string>;
  setSelected: (next: Set<string>) => void;
  onNext: () => void;
}) {
  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-base font-semibold">Select devices</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Only MikroTik (RouterOS) devices are supported by this wizard. Disabled
        devices are skipped automatically.
      </p>
      <div className="mt-4">
        <DevicePicker selected={selected} setSelected={setSelected} />
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="button"
          disabled={selected.size === 0}
          onClick={onNext}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          Continue ({selected.size})
        </button>
      </div>
    </section>
  );
}

// ---------------- Step 2: Settings ----------------

function SettingsStep({
  zabbixAddrs,
  setZabbixAddrs,
  addressList,
  setAddressList,
  community,
  setCommunity,
  snmpPort,
  setSnmpPort,
  configureCommunity,
  setConfigureCommunity,
  addrCount,
  onBack,
  onNext,
}: {
  zabbixAddrs: string;
  setZabbixAddrs: (v: string) => void;
  addressList: string;
  setAddressList: (v: string) => void;
  community: string;
  setCommunity: (v: string) => void;
  snmpPort: number;
  setSnmpPort: (v: number) => void;
  configureCommunity: boolean;
  setConfigureCommunity: (v: boolean) => void;
  addrCount: number;
  onBack: () => void;
  onNext: () => void;
}) {
  const [error, setError] = useState<string | null>(null);

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">SNMP / Zabbix settings</h2>
        <button
          type="button"
          onClick={onBack}
          className="text-xs text-muted-foreground hover:underline"
        >
          ← Devices
        </button>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (addrCount === 0) {
            setError("Enter at least one Zabbix IP or CIDR.");
            return;
          }
          if (!addressList.trim()) {
            setError("Address-list name is required.");
            return;
          }
          if (configureCommunity && !community.trim()) {
            setError("Community name is required (or turn off community setup).");
            return;
          }
          onNext();
        }}
        className="mt-4 space-y-4"
      >
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}

        <label className="block space-y-1 text-sm font-medium">
          Zabbix server IP(s) / CIDR
          <textarea
            required
            value={zabbixAddrs}
            onChange={(e) => setZabbixAddrs(e.target.value)}
            rows={2}
            className={`${input} font-mono`}
            placeholder="10.100.90.52, 10.100.90.0/24"
          />
          <span className="block text-[11px] font-normal text-muted-foreground">
            The source address(es) Zabbix polls from. Comma- or
            space-separated. Use a bare IP for a single host
            (e.g. <span className="font-mono">188.93.89.220</span>); a CIDR is
            treated as a whole subnet and snapped to its network address
            (<span className="font-mono">188.93.89.220/28</span> →{" "}
            <span className="font-mono">188.93.89.208/28</span>).
          </span>
        </label>

        <div className="grid gap-4 md:grid-cols-3">
          <label className="block space-y-1 text-sm font-medium">
            Address-list name
            <input
              required
              value={addressList}
              onChange={(e) => setAddressList(e.target.value)}
              className={`${input} font-mono`}
              placeholder="zabbix"
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            SNMP port
            <input
              type="number"
              min={1}
              max={65535}
              value={snmpPort}
              onChange={(e) => setSnmpPort(Number(e.target.value))}
              className={input}
            />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            Community (v2c)
            <input
              value={community}
              onChange={(e) => setCommunity(e.target.value)}
              disabled={!configureCommunity}
              className={`${input} font-mono disabled:opacity-50`}
              placeholder="public"
            />
          </label>
        </div>

        <label className="flex items-start gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
          <input
            type="checkbox"
            checked={configureCommunity}
            onChange={(e) => setConfigureCommunity(e.target.checked)}
            className="mt-0.5 size-4 rounded"
          />
          <span className="text-sm">
            <span className="font-medium">
              Configure the SNMP community and lock it to Zabbix
            </span>
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              Sets the community read-only and restricts its allowed addresses
              to the Zabbix IP(s). Uncheck to leave existing communities
              untouched.
            </span>
          </span>
        </label>

        <p className="rounded-md border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          SNMP is enabled via <span className="font-mono">/snmp</span> — on
          RouterOS it isn&apos;t an <span className="font-mono">/ip/service</span>{" "}
          entry. Access is restricted by the community addresses above plus the
          firewall rule, so there&apos;s no separate service ACL.
        </p>

        <div className="flex justify-end">
          <button
            type="submit"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Review
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- Step 3: Review & apply ----------------

function ApplyStep({
  deviceIds,
  zabbixAddresses,
  addressListName,
  communityName,
  snmpPort,
  configureCommunity,
  onBack,
}: {
  deviceIds: string[];
  zabbixAddresses: string[];
  addressListName: string;
  communityName: string;
  snmpPort: number;
  configureCommunity: boolean;
  onBack: () => void;
}) {
  const toast = useToast();
  const [result, setResult] = useState<BulkZabbixSnmpSetupResponse | null>(null);

  const m = useMutation<BulkZabbixSnmpSetupResponse>({
    mutationFn: () =>
      bulkZabbixSnmpSetup({
        device_ids: deviceIds,
        zabbix_addresses: zabbixAddresses,
        address_list_name: addressListName,
        snmp_port: snmpPort,
        community_name: communityName,
        configure_community: configureCommunity,
      }),
    onSuccess: (res) => {
      setResult(res);
      if (res.failed === 0) {
        toast.success(
          "SNMP configured",
          `${res.succeeded} device(s) ready for Zabbix`,
        );
      } else {
        toast.error(
          "Completed with errors",
          `${res.failed} of ${res.total} device(s) failed`,
        );
      }
    },
    onError: (e: Error) => toast.error("Bulk SNMP setup failed", e.message),
  });

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-border bg-card p-5">
        <div className="flex items-baseline justify-between">
          <h2 className="text-base font-semibold">Review</h2>
          <button
            type="button"
            onClick={onBack}
            className="text-xs text-muted-foreground hover:underline"
          >
            ← Settings
          </button>
        </div>

        <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
          <Row label="Devices" value={`${deviceIds.length} selected`} />
          <Row label="Zabbix IP(s)" value={zabbixAddresses.join(", ")} mono />
          <Row label="Address-list" value={addressListName} mono />
          <Row
            label="Firewall rule"
            value={`accept udp/${snmpPort} from address-list "${addressListName}" → top of input chain`}
          />
          <Row
            label="Community"
            value={
              configureCommunity
                ? `${communityName} (read-only, locked to Zabbix)`
                : "left untouched"
            }
            mono={configureCommunity}
          />
          <Row
            label="SNMP"
            value="enabled via /snmp (restricted by community + firewall)"
          />
        </dl>

        <p className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          Re-running is safe: duplicate address-list entries are ignored, the
          firewall rule is matched by its comment tag, and the community /
          service are updated in place.
        </p>

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            disabled={m.isPending}
            onClick={() => m.mutate()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending
              ? "Applying…"
              : `Apply to ${deviceIds.length} device(s)`}
          </button>
        </div>
      </div>

      {result && <ResultPanel {...result} />}
    </section>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border/60 py-1.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono text-xs" : "text-sm"}>{value}</dd>
    </div>
  );
}

// ---------------- Shared: device picker ----------------

function DevicePicker({
  selected,
  setSelected,
}: {
  selected: Set<string>;
  setSelected: (next: Set<string>) => void;
}) {
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: () => listSites(),
  });
  const siteIndex = useMemo(
    () => Object.fromEntries((sites ?? []).map((s) => [s.id, s.name])),
    [sites],
  );
  const [siteFilter, setSiteFilter] = useState("");

  const filteredDevices = useMemo(() => {
    if (!devices) return [];
    if (!siteFilter) return devices;
    return devices.filter((d) => d.site_id === siteFilter);
  }, [devices, siteFilter]);

  const allSelected =
    filteredDevices.length > 0 &&
    filteredDevices.every((d) => selected.has(d.id));

  function toggleAll() {
    const next = new Set(selected);
    if (allSelected) filteredDevices.forEach((d) => next.delete(d.id));
    else filteredDevices.forEach((d) => next.add(d.id));
    setSelected(next);
  }

  function toggleOne(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="space-y-1 text-xs font-medium text-muted-foreground">
          Filter by site
          <select
            value={siteFilter}
            onChange={(e) => setSiteFilter(e.target.value)}
            className={`${input} mt-1`}
          >
            <option value="">All sites</option>
            {sites?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <span className="text-xs text-muted-foreground">
          {selected.size} of {filteredDevices.length} selected
        </span>
      </div>
      <div className="mt-3 overflow-hidden rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="w-10 px-3 py-2">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="size-4 rounded"
                />
              </th>
              <th className="px-3 py-2 font-medium">Device</th>
              <th className="px-3 py-2 font-medium">Site</th>
              <th className="px-3 py-2 font-medium">Host</th>
              <th className="px-3 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredDevices.map((d) => (
              <tr key={d.id} className="hover:bg-accent/30">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={selected.has(d.id)}
                    onChange={() => toggleOne(d.id)}
                    className="size-4 rounded"
                  />
                </td>
                <td className="px-3 py-2 font-medium">{d.name}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  {siteIndex[d.site_id] ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{d.host}</td>
                <td className="px-3 py-2 text-xs text-muted-foreground">
                  {d.status}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------- Shared: result panel ----------------

function ResultPanel({
  total,
  succeeded,
  failed,
  skipped,
  results,
}: {
  total: number;
  succeeded: number;
  failed: number;
  skipped: number;
  results: BulkResult[];
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <h3 className="text-sm font-medium">Result</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        {succeeded} succeeded · {failed} failed · {skipped} skipped of {total}
      </p>
      <div className="mt-3 overflow-hidden rounded-md border border-border">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">Device</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {results.map((r) => (
              <tr key={r.device_id}>
                <td className="px-3 py-2">{r.device_name ?? r.device_id}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-md px-1.5 py-0.5 text-xs ${
                      r.status === "ok"
                        ? "bg-emerald-100 text-emerald-800"
                        : r.status === "skipped"
                          ? "bg-zinc-100 text-zinc-800"
                          : "bg-red-100 text-red-800"
                    }`}
                  >
                    {r.status}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                  {r.error ?? r.detail ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
