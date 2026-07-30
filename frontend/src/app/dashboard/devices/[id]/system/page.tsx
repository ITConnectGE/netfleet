"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { useToast } from "@/components/toast";
import { getDevice, rebootDevice, type Device } from "@/lib/devices";
import {
  capabilitiesFor,
  DRIVERS_QUERY_KEY,
  listDrivers,
  type Driver,
} from "@/lib/drivers";
import {
  createSnmpCommunity,
  deleteSnmpCommunity,
  getDeviceClock,
  updateDeviceClock,
  getNtp,
  getNtpServer,
  getSnmp,
  listSnmpCommunities,
  updateNtp,
  updateNtpServer,
  updateSnmp,
  updateSnmpCommunity,
  type DeviceClock,
  type NtpClient,
  type NtpServer,
  type SnmpCommunity,
  type SnmpSettings,
} from "@/lib/router-system";
import {
  LOGGING_TEMPLATES,
  createLoggingAction,
  createLoggingRule,
  deleteLoggingAction,
  deleteLoggingRule,
  listLoggingActions,
  listLoggingRules,
  updateLoggingRule,
  type LoggingAction,
  type LoggingActionTarget,
  type LoggingRule,
  type LoggingTemplate,
} from "@/lib/system-logging";

// Same capability gating as the outer device tabs: a Linux host has a clock
// and can reboot, but has no SNMP agent or RouterOS logging rules to show.
const TABS = [
  { id: "clock", label: "Clock & time zone", needs: "system.clock" },
  { id: "ntp", label: "NTP", needs: "system.clock" },
  { id: "snmp", label: "SNMP", needs: "system.snmp" },
  { id: "logging", label: "Logging", needs: "system.log" },
  { id: "reboot", label: "Reboot", needs: "system.reboot" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function isTabId(v: string | null): v is TabId {
  return v != null && TABS.some((t) => t.id === v);
}

export default function SystemPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const { data: device } = useQuery<Device>({
    queryKey: ["device", deviceId],
    queryFn: () => getDevice(deviceId),
    enabled: Boolean(deviceId),
  });
  const { data: drivers } = useQuery<Driver[]>({
    queryKey: DRIVERS_QUERY_KEY,
    queryFn: listDrivers,
    staleTime: 5 * 60_000,
  });
  const caps = capabilitiesFor(drivers, device?.vendor);
  const tabs = caps ? TABS.filter((t) => caps.has(t.needs)) : TABS;

  const rawTab = searchParams.get("tab");
  const requested: TabId = isTabId(rawTab) ? rawTab : "clock";
  // A deep link to a tab this device does not have (a bookmark, or a link
  // shared from a RouterOS device) falls back to the first one it does.
  const activeTab: TabId =
    tabs.some((t) => t.id === requested) || tabs.length === 0
      ? requested
      : tabs[0].id;

  // Build href once per tab so the buttons render as real anchors —
  // keeps deep-linking + back-button behaviour the way users expect.
  const tabHrefs = useMemo(
    () =>
      TABS.reduce<Record<TabId, string>>((acc, t) => {
        acc[t.id] = `${pathname}?tab=${t.id}`;
        return acc;
      }, {} as Record<TabId, string>),
    [pathname],
  );

  function selectTab(id: TabId) {
    router.replace(tabHrefs[id], { scroll: false });
  }

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight">System</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Configure router-side services. Changes apply directly to the device.
      </p>

      <div className="mt-4 border-b border-border">
        <nav className="-mb-px flex flex-wrap gap-1" aria-label="System sub-pages">
          {tabs.map((t) => {
            const active = t.id === activeTab;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => selectTab(t.id)}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "border-b-2 border-primary px-3 py-2 text-sm font-medium text-primary"
                    : "border-b-2 border-transparent px-3 py-2 text-sm font-medium text-muted-foreground hover:border-border hover:text-foreground"
                }
              >
                {t.label}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="mt-6 space-y-10">
        {activeTab === "clock" && (
          <>
            <ClockCard deviceId={deviceId} />
            <TimeZoneSection deviceId={deviceId} />
          </>
        )}
        {activeTab === "ntp" && (
          <>
            <NtpSection deviceId={deviceId} />
            <NtpServerSection deviceId={deviceId} />
          </>
        )}
        {activeTab === "snmp" && (
          <>
            <SnmpSection deviceId={deviceId} />
            <SnmpCommunitiesSection deviceId={deviceId} />
          </>
        )}
        {activeTab === "logging" && <LoggingSection deviceId={deviceId} />}
        {activeTab === "reboot" && <RebootSection deviceId={deviceId} />}
      </div>
    </div>
  );
}

// ---------------- Reboot ----------------

function RebootSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [confirmText, setConfirmText] = useState("");

  const { data: device } = useQuery<Device>({
    queryKey: ["device", deviceId],
    queryFn: () => getDevice(deviceId),
  });

  const reboot = useMutation({
    mutationFn: () => rebootDevice(deviceId),
    onSuccess: () => {
      setConfirmText("");
      qc.invalidateQueries({ queryKey: ["device", deviceId] });
      toast.success(
        "Reboot triggered",
        "The router will be back online in 1–3 minutes. Re-run Test Connection then.",
      );
    },
    onError: (e: Error) => toast.error("Reboot failed", e.message),
  });

  const expected = device?.name ?? "";
  const armed = confirmText.trim() === expected && expected !== "";

  return (
    <section>
      <h2 className="text-lg font-semibold">Reboot</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Cleanly reboots the device via{" "}
        <span className="font-mono">/system/reboot</span>. Active sessions and
        traffic through the router are interrupted for ~1–3 minutes.
      </p>

      <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50/60 p-5">
        <h3 className="text-sm font-semibold text-amber-900">
          ⚠ Destructive — confirm the device name to arm
        </h3>
        <p className="mt-1 text-xs text-amber-900/80">
          Type{" "}
          <span className="font-mono">
            {expected || "(loading…)"}
          </span>{" "}
          below to enable the Reboot button. Closes the API session, drops the
          uplink, may require a couple of minutes before the device responds
          again.
        </p>
        <input
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="device name"
          className="mt-3 block w-full max-w-sm rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <div className="mt-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => reboot.mutate()}
            disabled={!armed || reboot.isPending}
            className="rounded-md border border-amber-400 bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {reboot.isPending ? "Rebooting…" : "Reboot device"}
          </button>
          <span className="text-xs text-muted-foreground">
            Audit log entry will record this action.
          </span>
        </div>
      </div>

      <p className="mt-3 text-xs text-muted-foreground">
        Need to upgrade firmware instead? Use the Firmware card on the device
        overview — it reboots automatically as part of the upgrade.
      </p>
    </section>
  );
}

// ---------------- NTP ----------------

function NtpSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery<NtpClient>({
    queryKey: ["ntp", deviceId],
    queryFn: () => getNtp(deviceId),
  });

  const [enabled, setEnabled] = useState(true);
  const [mode, setMode] = useState("unicast");
  const [servers, setServers] = useState("");
  const [done, setDone] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setEnabled(data.enabled);
      setMode(data.mode || "unicast");
      setServers(data.servers || [data.primary, data.secondary].filter(Boolean).join(","));
    }
  }, [data]);

  const m = useMutation({
    mutationFn: () =>
      updateNtp(deviceId, {
        enabled,
        mode: mode as "unicast" | "broadcast" | "multicast" | "manycast",
        servers: servers || null,
      }),
    onSuccess: () => {
      setDone(true);
      qc.invalidateQueries({ queryKey: ["ntp", deviceId] });
      setTimeout(() => setDone(false), 3000);
    },
    onError: (e: Error) => setErrMsg(e.message),
  });

  return (
    <section>
      <h2 className="text-lg font-semibold">NTP client</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Keep router clocks in sync — required for accurate logs, certificates and audit timestamps.
      </p>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}
      {errMsg && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errMsg}
        </div>
      )}
      {done && (
        <div className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          NTP settings updated.
        </div>
      )}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setErrMsg(null);
          m.mutate();
        }}
        className="mt-4 rounded-lg border border-border bg-card p-5"
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="size-4 rounded"
            disabled={isLoading}
          />
          NTP client enabled
        </label>

        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <Field label="Mode" htmlFor="n-mode">
            <select
              id="n-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className={input}
              disabled={isLoading || !enabled}
            >
              <option value="unicast">unicast</option>
              <option value="broadcast">broadcast</option>
              <option value="multicast">multicast</option>
              <option value="manycast">manycast</option>
            </select>
          </Field>
          <Field label="Servers (comma-separated DNS / IPs)" htmlFor="n-srv">
            <input
              id="n-srv"
              value={servers}
              onChange={(e) => setServers(e.target.value)}
              className={`${input} font-mono`}
              placeholder="0.pool.ntp.org,1.pool.ntp.org,time.google.com"
              disabled={isLoading || !enabled}
            />
          </Field>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="submit"
            disabled={m.isPending || isLoading}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Saving…" : "Save NTP settings"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- SNMP ----------------

function SnmpSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<SnmpSettings>({
    queryKey: ["snmp", deviceId],
    queryFn: () => getSnmp(deviceId),
  });

  const [enabled, setEnabled] = useState(false);
  const [contact, setContact] = useState("");
  const [location, setLocation] = useState("");
  const [trapTarget, setTrapTarget] = useState("");
  const [trapVersion, setTrapVersion] = useState<"1" | "2" | "3">("2");
  const [done, setDone] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setEnabled(data.enabled);
      setContact(data.contact ?? "");
      setLocation(data.location ?? "");
      setTrapTarget(data.trap_target ?? "");
      if (data.trap_version === "1" || data.trap_version === "2" || data.trap_version === "3") {
        setTrapVersion(data.trap_version);
      }
    }
  }, [data]);

  const m = useMutation({
    mutationFn: () =>
      updateSnmp(deviceId, {
        enabled,
        contact: contact || null,
        location: location || null,
        trap_target: trapTarget || null,
        trap_version: trapVersion,
      }),
    onSuccess: () => {
      setDone(true);
      qc.invalidateQueries({ queryKey: ["snmp", deviceId] });
      setTimeout(() => setDone(false), 3000);
    },
    onError: (e: Error) => setErrMsg(e.message),
  });

  return (
    <section>
      <h2 className="text-lg font-semibold">SNMP</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Enable SNMP for monitoring (read-only) or for control (read-write — be careful).
        Configure at least one community below to actually allow polling.
      </p>

      {errMsg && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errMsg}
        </div>
      )}
      {done && (
        <div className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          SNMP settings updated.
        </div>
      )}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setErrMsg(null);
          m.mutate();
        }}
        className="mt-4 rounded-lg border border-border bg-card p-5"
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="size-4 rounded"
            disabled={isLoading}
          />
          SNMP service enabled
        </label>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Contact" htmlFor="s-c">
            <input
              id="s-c"
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              className={input}
              placeholder="noc@itconnect.ge"
              disabled={isLoading || !enabled}
            />
          </Field>
          <Field label="Location" htmlFor="s-l">
            <input
              id="s-l"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className={input}
              placeholder="Client A, server room 1"
              disabled={isLoading || !enabled}
            />
          </Field>
          <Field label="Trap target" htmlFor="s-tt" hint="ip[:port], comma-separated">
            <input
              id="s-tt"
              value={trapTarget}
              onChange={(e) => setTrapTarget(e.target.value)}
              className={`${input} font-mono`}
              placeholder="10.0.0.5:162"
              disabled={isLoading || !enabled}
            />
          </Field>
          <Field label="Trap version" htmlFor="s-tv">
            <select
              id="s-tv"
              value={trapVersion}
              onChange={(e) => setTrapVersion(e.target.value as "1" | "2" | "3")}
              className={input}
              disabled={isLoading || !enabled}
            >
              <option value="1">v1</option>
              <option value="2">v2c</option>
              <option value="3">v3</option>
            </select>
          </Field>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="submit"
            disabled={m.isPending || isLoading}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Saving…" : "Save SNMP settings"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- SNMP communities ----------------

function SnmpCommunitiesSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data: items, isLoading } = useQuery<SnmpCommunity[]>({
    queryKey: ["snmp-communities", deviceId],
    queryFn: () => listSnmpCommunities(deviceId),
  });

  const [showForm, setShowForm] = useState(false);
  const del = useMutation({
    mutationFn: (id: string) => deleteSnmpCommunity(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["snmp-communities", deviceId] }),
  });

  return (
    <section>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">SNMP communities</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Per-community access. Default <code>public</code> is read-only. Add a write community
            only if you really need it.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New community"}
        </button>
      </div>

      {showForm && (
        <CommunityForm
          deviceId={deviceId}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["snmp-communities", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Allowed from</th>
              <th className="px-4 py-2.5 font-medium">Read</th>
              <th className="px-4 py-2.5 font-medium">Write</th>
              <th className="px-4 py-2.5 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-5 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (!items || items.length === 0) && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  No SNMP communities defined.
                </td>
              </tr>
            )}
            {items?.map((c) => (
              <CommunityRow
                key={c.id ?? c.name}
                community={c}
                deviceId={deviceId}
                onDelete={() => {
                  if (c.id && confirm(`Delete SNMP community "${c.name}"?`)) {
                    del.mutate(c.id);
                  }
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CommunityRow({
  community,
  deviceId,
  onDelete,
}: {
  community: SnmpCommunity;
  deviceId: string;
  onDelete: () => void;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  // Local form state — only synced from props when the user enters edit
  // mode, so they keep their unsaved typing across a refetch.
  const [addresses, setAddresses] = useState(community.addresses ?? "");
  const [readAccess, setReadAccess] = useState(community.read_access);
  const [writeAccess, setWriteAccess] = useState(community.write_access);
  const [disabled, setDisabled] = useState(community.disabled);
  const [error, setError] = useState<string | null>(null);

  function startEditing() {
    setAddresses(community.addresses ?? "");
    setReadAccess(community.read_access);
    setWriteAccess(community.write_access);
    setDisabled(community.disabled);
    setError(null);
    setEditing(true);
  }

  const save = useMutation({
    mutationFn: () => {
      if (!community.id) return Promise.reject(new Error("missing community id"));
      return updateSnmpCommunity(deviceId, community.id, {
        // Send empty string verbatim — RouterOS treats it as "any source".
        addresses,
        read_access: readAccess,
        write_access: writeAccess,
        disabled,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["snmp-communities", deviceId] });
      setEditing(false);
    },
    onError: (e: Error) => setError(e.message),
  });

  if (!editing) {
    return (
      <tr className="hover:bg-accent/30">
        <td className="px-4 py-2.5 font-medium">
          {community.name}
          {community.disabled && (
            <span className="ml-2 rounded-md bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-800">
              disabled
            </span>
          )}
        </td>
        <td className="px-4 py-2.5 font-mono text-xs">
          {community.addresses ?? "any"}
        </td>
        <td className="px-4 py-2.5 text-xs">
          {community.read_access ? (
            <span className="text-emerald-700">✓</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-4 py-2.5 text-xs">
          {community.write_access ? (
            <span className="text-amber-700">⚠ write</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-4 py-2.5 text-right text-xs">
          {community.id && (
            <button
              type="button"
              onClick={startEditing}
              className="mr-3 text-primary hover:underline"
            >
              Edit
            </button>
          )}
          <button
            type="button"
            onClick={onDelete}
            className="text-destructive hover:underline"
          >
            Delete
          </button>
        </td>
      </tr>
    );
  }

  return (
    <tr className="bg-accent/20">
      <td className="px-4 py-2.5 font-medium align-top">
        {community.name}
        <div className="mt-1">
          <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <input
              type="checkbox"
              checked={disabled}
              onChange={(e) => setDisabled(e.target.checked)}
              className="size-3"
            />
            disabled
          </label>
        </div>
      </td>
      <td className="px-4 py-2.5 align-top">
        <input
          value={addresses}
          onChange={(e) => setAddresses(e.target.value)}
          placeholder="10.0.0.0/24,192.168.1.5"
          className="block w-full rounded-md border border-input bg-background px-2 py-1 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          Blank = any source
        </p>
        {error && (
          <p className="mt-1 text-[11px] text-destructive">{error}</p>
        )}
      </td>
      <td className="px-4 py-2.5 align-top">
        <input
          type="checkbox"
          checked={readAccess}
          onChange={(e) => setReadAccess(e.target.checked)}
          className="size-4"
        />
      </td>
      <td className="px-4 py-2.5 align-top">
        <input
          type="checkbox"
          checked={writeAccess}
          onChange={(e) => setWriteAccess(e.target.checked)}
          className="size-4"
        />
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 text-right text-xs align-top">
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="mr-2 rounded-md bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => {
            setError(null);
            setEditing(false);
          }}
          className="text-muted-foreground hover:underline"
        >
          Cancel
        </button>
      </td>
    </tr>
  );
}

function CommunityForm({
  deviceId,
  onCreated,
}: {
  deviceId: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [addresses, setAddresses] = useState("");
  const [readAccess, setReadAccess] = useState(true);
  const [writeAccess, setWriteAccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createSnmpCommunity(deviceId, {
        name,
        addresses: addresses || null,
        read_access: readAccess,
        write_access: writeAccess,
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        setError(null);
        m.mutate();
      }}
      className="mt-4 rounded-lg border border-border bg-card p-5"
    >
      {error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Name" htmlFor="c-n">
          <input
            id="c-n"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="public"
          />
        </Field>
        <Field
          label="Allowed source addresses"
          htmlFor="c-a"
          hint="e.g. 10.0.0.0/24, blank = anywhere"
        >
          <input
            id="c-a"
            value={addresses}
            onChange={(e) => setAddresses(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.0/24,192.168.1.5"
          />
        </Field>
      </div>
      <div className="mt-4 flex items-center gap-6 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={readAccess}
            onChange={(e) => setReadAccess(e.target.checked)}
            className="size-4 rounded"
          />
          Read access
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={writeAccess}
            onChange={(e) => setWriteAccess(e.target.checked)}
            className="size-4 rounded"
          />
          <span>Write access <span className="text-xs text-amber-700">(dangerous)</span></span>
        </label>
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create community"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
        {hint && <span className="ml-2 text-xs font-normal text-muted-foreground">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";

// ---------------- Time zone ----------------

// Curated short-list of common IANA tz names; the field accepts any string,
// but giving operators a one-click dropdown for the usual suspects cuts the
// "what was the exact spelling?" friction. RouterOS accepts the literal
// "manual" for offset-only configuration.
const TIMEZONE_PRESETS: string[] = [
  "Asia/Tbilisi",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Moscow",
  "Europe/Istanbul",
  "Asia/Baku",
  "Asia/Yerevan",
  "Asia/Dubai",
  "Asia/Tehran",
  "Asia/Tashkent",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "Australia/Sydney",
  "UTC",
  "manual",
];

function TimeZoneSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery<DeviceClock>({
    queryKey: ["clock", deviceId],
    queryFn: () => getDeviceClock(deviceId),
  });

  const [tz, setTz] = useState<string>("");
  const [autodetect, setAutodetect] = useState<boolean>(false);
  const [touched, setTouched] = useState(false);
  const [done, setDone] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!data || touched) return;
    setTz(data.time_zone_name ?? "");
    setAutodetect(data.time_zone_autodetect ?? false);
  }, [data, touched]);

  const m = useMutation({
    mutationFn: () =>
      updateDeviceClock(deviceId, {
        time_zone_name: tz || null,
        time_zone_autodetect: autodetect,
      }),
    onSuccess: () => {
      setDone(true);
      setTouched(false);
      qc.invalidateQueries({ queryKey: ["clock", deviceId] });
      window.setTimeout(() => setDone(false), 2500);
    },
    onError: (e: Error) => setErrMsg(e.message),
  });

  return (
    <section>
      <h2 className="text-lg font-semibold">Time zone</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        IANA tz database name (the same strings the OS uses). Disable
        autodetect when you want a fixed zone regardless of the device&apos;s
        WAN-derived location.
      </p>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}
      {errMsg && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errMsg}
        </div>
      )}
      {done && (
        <div className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          Time zone updated.
        </div>
      )}

      <div className="mt-4 grid gap-4 rounded-lg border border-border bg-card p-5 md:grid-cols-[1fr_1fr_auto]">
        <label className="block space-y-1 text-xs">
          <span className="font-medium text-muted-foreground">Time zone</span>
          <div className="flex items-center gap-2">
            <input
              list="tz-presets"
              value={tz}
              onChange={(e) => {
                setTz(e.target.value);
                setTouched(true);
                setErrMsg(null);
              }}
              placeholder="Asia/Tbilisi"
              disabled={isLoading}
              className={input}
            />
            <datalist id="tz-presets">
              {TIMEZONE_PRESETS.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
          </div>
          <span className="block text-[10px] text-muted-foreground">
            Type any IANA name or pick one from the dropdown.
          </span>
        </label>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={autodetect}
            onChange={(e) => {
              setAutodetect(e.target.checked);
              setTouched(true);
              setErrMsg(null);
            }}
            className="size-4 rounded"
          />
          Autodetect from WAN location
        </label>

        <div className="flex items-end">
          <button
            type="button"
            onClick={() => {
              setErrMsg(null);
              m.mutate();
            }}
            disabled={!touched || m.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </section>
  );
}

// ---------------- Device clock ----------------

function ClockCard({ deviceId }: { deviceId: string }) {
  const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery<DeviceClock>({
    queryKey: ["clock", deviceId],
    queryFn: () => getDeviceClock(deviceId),
    refetchInterval: 10_000,
  });

  return (
    <section>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Device time</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Live from the router. Auto-refreshes every 10 seconds — large drift here means
            NTP isn&apos;t reaching the device.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-xs hover:bg-accent"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      <div className="mt-4 rounded-lg border border-border bg-card p-5">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KV label="Time">
              <span className="font-mono text-2xl tabular-nums">
                {data?.time ?? "—"}
              </span>
            </KV>
            <KV label="Date">
              <span className="font-mono">{data?.date ?? "—"}</span>
            </KV>
            <KV label="Timezone">
              <span className="font-mono text-sm">
                {data?.time_zone_name ?? "—"}
                {data?.gmt_offset && (
                  <span className="ml-1 text-xs text-muted-foreground">
                    ({data.gmt_offset})
                  </span>
                )}
                {data?.time_zone_autodetect && (
                  <span className="ml-1 text-[10px] uppercase text-muted-foreground">
                    auto
                  </span>
                )}
              </span>
            </KV>
            <KV label="DST">
              {data?.dst_active === null || data?.dst_active === undefined ? (
                <span className="text-muted-foreground">—</span>
              ) : data.dst_active ? (
                <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] text-sky-900">
                  active
                </span>
              ) : (
                <span className="text-muted-foreground">off</span>
              )}
            </KV>
          </div>
        )}
        {dataUpdatedAt > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            updated {new Date(dataUpdatedAt).toLocaleTimeString()}
          </p>
        )}
      </div>
    </section>
  );
}

function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1">{children}</div>
    </div>
  );
}

// ---------------- NTP server ----------------

function NtpServerSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<NtpServer>({
    queryKey: ["ntp-server", deviceId],
    queryFn: () => getNtpServer(deviceId),
  });

  const [enabled, setEnabled] = useState(false);
  const [broadcast, setBroadcast] = useState(false);
  const [multicast, setMulticast] = useState(false);
  const [manycast, setManycast] = useState(false);
  const [done, setDone] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setEnabled(data.enabled);
      setBroadcast(Boolean(data.broadcast));
      setMulticast(Boolean(data.multicast));
      setManycast(Boolean(data.manycast));
    }
  }, [data]);

  const m = useMutation({
    mutationFn: () =>
      updateNtpServer(deviceId, { enabled, broadcast, multicast, manycast }),
    onSuccess: () => {
      setDone(true);
      qc.invalidateQueries({ queryKey: ["ntp-server", deviceId] });
      setTimeout(() => setDone(false), 3000);
    },
    onError: (e: Error) => setErrMsg(e.message),
  });

  return (
    <section>
      <h2 className="text-lg font-semibold">NTP server</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Let other devices on the LAN sync their clock from this router. Enable only one of
        broadcast/multicast/manycast depending on your network design — leave them all off
        for plain unicast service.
      </p>

      {errMsg && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errMsg}
        </div>
      )}
      {done && (
        <div className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          NTP server settings updated.
        </div>
      )}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setErrMsg(null);
          m.mutate();
        }}
        className="mt-4 rounded-lg border border-border bg-card p-5"
      >
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="size-4 rounded"
            disabled={isLoading}
          />
          NTP server enabled
        </label>

        <div className="mt-4 flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={broadcast}
              onChange={(e) => setBroadcast(e.target.checked)}
              className="size-4 rounded"
              disabled={isLoading || !enabled}
            />
            broadcast
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={multicast}
              onChange={(e) => setMulticast(e.target.checked)}
              className="size-4 rounded"
              disabled={isLoading || !enabled}
            />
            multicast
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={manycast}
              onChange={(e) => setManycast(e.target.checked)}
              className="size-4 rounded"
              disabled={isLoading || !enabled}
            />
            manycast
          </label>
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="submit"
            disabled={m.isPending || isLoading}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Saving…" : "Save NTP server settings"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- Logging ----------------

function LoggingSection({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();

  const { data: rules, isLoading: rulesLoading, error: rulesError } = useQuery<
    LoggingRule[]
  >({
    queryKey: ["logging-rules", deviceId],
    queryFn: () => listLoggingRules(deviceId),
  });
  const { data: actions, isLoading: actionsLoading } = useQuery<LoggingAction[]>({
    queryKey: ["logging-actions", deviceId],
    queryFn: () => listLoggingActions(deviceId),
  });

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ["logging-rules", deviceId] });
    qc.invalidateQueries({ queryKey: ["logging-actions", deviceId] });
  };

  const applyTemplate = useMutation({
    mutationFn: (tpl: LoggingTemplate) =>
      createLoggingRule(deviceId, {
        topics: tpl.topics,
        action: tpl.action,
        prefix: tpl.prefix ?? null,
        disabled: false,
      }),
    onSuccess: (_data, tpl) => {
      toast.success("Logging rule added", tpl.label);
      refreshAll();
    },
    onError: (e: Error) => toast.error("Apply failed", e.message),
  });

  const toggleRule = useMutation({
    mutationFn: ({ id, disabled }: { id: string; disabled: boolean }) =>
      updateLoggingRule(deviceId, id, { disabled }),
    onSuccess: refreshAll,
    onError: (e: Error) => toast.error("Update failed", e.message),
  });

  const removeRule = useMutation({
    mutationFn: (id: string) => deleteLoggingRule(deviceId, id),
    onSuccess: refreshAll,
    onError: (e: Error) => toast.error("Delete failed", e.message),
  });

  const removeAction = useMutation({
    mutationFn: (id: string) => deleteLoggingAction(deviceId, id),
    onSuccess: refreshAll,
    onError: (e: Error) => toast.error("Delete failed", e.message),
  });

  const [showAddRule, setShowAddRule] = useState(false);
  const [showAddAction, setShowAddAction] = useState(false);

  return (
    <>
      <section className="rounded-lg border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Templates</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              One-click rules for common scenarios. Each template appends a
              new entry to <code>/system logging</code> on the device; you can
              tweak topics or action afterwards from the table below.
            </p>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {LOGGING_TEMPLATES.map((tpl) => (
            <div
              key={tpl.key}
              className="rounded-md border border-border bg-background p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold">{tpl.label}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {tpl.description}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => applyTemplate.mutate(tpl)}
                  disabled={applyTemplate.isPending}
                  className="shrink-0 rounded-md border border-input bg-card px-2 py-1 text-xs font-medium transition hover:bg-accent disabled:opacity-50"
                >
                  Apply
                </button>
              </div>
              <div className="mt-2 flex flex-wrap gap-1 font-mono text-[10px] text-muted-foreground">
                <span className="rounded bg-muted px-1.5 py-0.5">
                  topics={tpl.topics}
                </span>
                <span className="rounded bg-muted px-1.5 py-0.5">
                  action={tpl.action}
                </span>
                {tpl.prefix && (
                  <span className="rounded bg-muted px-1.5 py-0.5">
                    prefix=&quot;{tpl.prefix}&quot;
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Rules</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Each rule maps a comma-separated topic filter to a logging
              action. The default seed rules (info → memory, etc.) are kept
              read-only.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowAddRule((s) => !s)}
            className="shrink-0 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          >
            {showAddRule ? "Cancel" : "+ Custom rule"}
          </button>
        </div>

        {showAddRule && (
          <AddRuleForm
            deviceId={deviceId}
            actions={actions ?? []}
            onDone={() => {
              setShowAddRule(false);
              refreshAll();
            }}
          />
        )}

        {rulesError && (
          <p className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {(rulesError as Error).message}
          </p>
        )}

        <div className="mt-4 overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Topics</th>
                <th className="px-3 py-2 font-medium">Action</th>
                <th className="px-3 py-2 font-medium">Prefix</th>
                <th className="px-3 py-2 font-medium">State</th>
                <th className="px-3 py-2 font-medium text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rulesLoading && (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-xs text-muted-foreground">
                    Loading…
                  </td>
                </tr>
              )}
              {!rulesLoading && (rules?.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-xs text-muted-foreground">
                    No logging rules on this device.
                  </td>
                </tr>
              )}
              {rules?.map((r) => (
                <tr key={r.id ?? `${r.topics}-${r.action}`} className="hover:bg-accent/30">
                  <td className="px-3 py-2 font-mono text-xs">{r.topics}</td>
                  <td className="px-3 py-2 text-xs">
                    <span className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                      {r.action}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">
                    {r.prefix ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {r.default && (
                      <span className="mr-1 rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-700">
                        default
                      </span>
                    )}
                    {r.invalid && (
                      <span className="mr-1 rounded-md bg-red-100 px-1.5 py-0.5 text-[10px] text-red-800">
                        invalid
                      </span>
                    )}
                    {r.disabled ? (
                      <span className="rounded-md bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-700">
                        disabled
                      </span>
                    ) : (
                      <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800">
                        active
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right text-xs">
                    {!r.default && r.id && (
                      <>
                        <button
                          onClick={() =>
                            toggleRule.mutate({ id: r.id!, disabled: !r.disabled })
                          }
                          className="mr-3 text-muted-foreground hover:underline"
                        >
                          {r.disabled ? "Enable" : "Disable"}
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Delete this rule? (topics=${r.topics})`)) {
                              removeRule.mutate(r.id!);
                            }
                          }}
                          className="text-destructive hover:underline"
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-border bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Actions</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Where matched lines land. <code>memory</code> / <code>disk</code> /{" "}
              <code>echo</code> are built in; add a <code>remote</code> action
              to forward to a central syslog (e.g. Graylog, Wazuh,
              Logstash).
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowAddAction((s) => !s)}
            className="shrink-0 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          >
            {showAddAction ? "Cancel" : "+ Remote syslog"}
          </button>
        </div>

        {showAddAction && (
          <AddActionForm
            deviceId={deviceId}
            onDone={() => {
              setShowAddAction(false);
              refreshAll();
            }}
          />
        )}

        <div className="mt-4 overflow-hidden rounded-md border border-border">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Target</th>
                <th className="px-3 py-2 font-medium">Details</th>
                <th className="px-3 py-2 font-medium text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {actionsLoading && (
                <tr>
                  <td colSpan={4} className="px-3 py-4 text-center text-xs text-muted-foreground">
                    Loading…
                  </td>
                </tr>
              )}
              {actions?.map((a) => (
                <tr key={a.id ?? a.name} className="hover:bg-accent/30">
                  <td className="px-3 py-2 font-mono text-xs">{a.name}</td>
                  <td className="px-3 py-2 text-xs">
                    <span className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                      {a.target}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-[11px] text-muted-foreground">
                    {a.target === "remote" && (
                      <span className="font-mono">
                        {a.remote}:{a.remote_port ?? 514}
                        {a.syslog_severity && ` · severity ≥ ${a.syslog_severity}`}
                      </span>
                    )}
                    {a.target === "memory" && a.memory_lines != null && (
                      <span className="font-mono">{a.memory_lines} lines</span>
                    )}
                    {a.target === "disk" && a.disk_lines_per_file != null && (
                      <span className="font-mono">
                        {a.disk_lines_per_file} lines × {a.disk_file_count ?? 0} files
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right text-xs">
                    {!a.default && a.id && (
                      <button
                        onClick={() => {
                          if (confirm(`Delete action "${a.name}"?`)) {
                            removeAction.mutate(a.id!);
                          }
                        }}
                        className="text-destructive hover:underline"
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function AddRuleForm({
  deviceId,
  actions,
  onDone,
}: {
  deviceId: string;
  actions: LoggingAction[];
  onDone: () => void;
}) {
  const toast = useToast();
  const [topics, setTopics] = useState("");
  const [action, setAction] = useState("memory");
  const [prefix, setPrefix] = useState("");
  const [disabled, setDisabled] = useState(false);

  const m = useMutation({
    mutationFn: () =>
      createLoggingRule(deviceId, {
        topics,
        action,
        prefix: prefix || null,
        disabled,
      }),
    onSuccess: () => {
      toast.success("Rule added");
      onDone();
    },
    onError: (e: Error) => toast.error("Add failed", e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!topics.trim()) {
      toast.error("Topics required");
      return;
    }
    m.mutate();
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mt-4 grid gap-3 rounded-md border border-border bg-background p-4 md:grid-cols-4"
    >
      <label className="md:col-span-2 space-y-1">
        <span className="text-xs font-medium text-muted-foreground">Topics</span>
        <input
          value={topics}
          onChange={(e) => setTopics(e.target.value)}
          placeholder="firewall,!info"
          className="block w-full rounded-md border border-input bg-card px-3 py-1.5 font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </label>
      <label className="space-y-1">
        <span className="text-xs font-medium text-muted-foreground">Action</span>
        <select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="block w-full rounded-md border border-input bg-card px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {actions.length === 0 && <option value="memory">memory</option>}
          {actions.map((a) => (
            <option key={a.id ?? a.name} value={a.name}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <label className="space-y-1">
        <span className="text-xs font-medium text-muted-foreground">Prefix (optional)</span>
        <input
          value={prefix}
          onChange={(e) => setPrefix(e.target.value)}
          placeholder="fw-drop"
          className="block w-full rounded-md border border-input bg-card px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </label>
      <div className="md:col-span-4 flex items-center justify-between">
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={disabled}
            onChange={(e) => setDisabled(e.target.checked)}
            className="size-4 rounded"
          />
          Create disabled (toggle on later)
        </label>
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Adding…" : "Add rule"}
        </button>
      </div>
    </form>
  );
}

function AddActionForm({
  deviceId,
  onDone,
}: {
  deviceId: string;
  onDone: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [target, setTarget] = useState<LoggingActionTarget>("remote");
  const [remote, setRemote] = useState("");
  const [remotePort, setRemotePort] = useState<number>(514);
  const [severity, setSeverity] = useState("warning");
  const [bsdSyslog, setBsdSyslog] = useState(true);

  const m = useMutation({
    mutationFn: () =>
      createLoggingAction(deviceId, {
        name,
        target,
        remote: target === "remote" ? remote : null,
        remote_port: target === "remote" ? remotePort : null,
        syslog_severity: target === "remote" ? severity : null,
        bsd_syslog: target === "remote" ? bsdSyslog : null,
      }),
    onSuccess: () => {
      toast.success("Action added");
      onDone();
    },
    onError: (e: Error) => toast.error("Add failed", e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      toast.error("Name required");
      return;
    }
    if (target === "remote" && !remote.trim()) {
      toast.error("Remote syslog server required");
      return;
    }
    m.mutate();
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mt-4 grid gap-3 rounded-md border border-border bg-background p-4 md:grid-cols-4"
    >
      <label className="space-y-1">
        <span className="text-xs font-medium text-muted-foreground">Name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="graylog"
          className="block w-full rounded-md border border-input bg-card px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </label>
      <label className="space-y-1">
        <span className="text-xs font-medium text-muted-foreground">Target</span>
        <select
          value={target}
          onChange={(e) => setTarget(e.target.value as LoggingActionTarget)}
          className="block w-full rounded-md border border-input bg-card px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="remote">remote (syslog)</option>
          <option value="memory">memory</option>
          <option value="disk">disk</option>
          <option value="echo">echo</option>
        </select>
      </label>
      {target === "remote" && (
        <>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Server</span>
            <input
              value={remote}
              onChange={(e) => setRemote(e.target.value)}
              placeholder="10.0.0.10"
              className="block w-full rounded-md border border-input bg-card px-3 py-1.5 font-mono text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Port</span>
            <input
              type="number"
              min={1}
              max={65535}
              value={remotePort}
              onChange={(e) => setRemotePort(Number(e.target.value))}
              className="block w-full rounded-md border border-input bg-card px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">Min severity</span>
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
              className="block w-full rounded-md border border-input bg-card px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
            >
              <option value="debug">debug</option>
              <option value="info">info</option>
              <option value="notice">notice</option>
              <option value="warning">warning</option>
              <option value="error">error</option>
              <option value="critical">critical</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-muted-foreground md:col-span-2">
            <input
              type="checkbox"
              checked={bsdSyslog}
              onChange={(e) => setBsdSyslog(e.target.checked)}
              className="size-4 rounded"
            />
            BSD syslog framing (RFC 3164) — turn off only for RFC 5424 collectors
          </label>
        </>
      )}
      <div className="md:col-span-4 flex items-center justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Adding…" : "Add action"}
        </button>
      </div>
    </form>
  );
}
