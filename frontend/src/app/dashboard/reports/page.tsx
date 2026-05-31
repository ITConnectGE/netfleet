"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import {
  changeReport,
  deviceActivityReport,
  downloadReportCsv,
  secretAccessReport,
  userActivityReport,
  type ChangeReport,
  type DeviceActivityReport,
  type SecretAccessReport,
  type UserActivityReport,
} from "@/lib/reports";

type Tab = "user" | "device" | "secret" | "changes";

function isoStartOf(daysAgo: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - daysAgo);
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString();
}
function isoNow(): string {
  return new Date().toISOString();
}
function toLocal(iso: string): string {
  return new Date(iso).toLocaleString();
}
function toDateInput(iso: string): string {
  // datetime-local needs YYYY-MM-DDTHH:mm (no seconds, no Z)
  return new Date(iso).toISOString().slice(0, 16);
}
function fromDateInput(v: string): string {
  return new Date(v).toISOString();
}

export default function ReportsPage() {
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("user");
  const [tsFrom, setTsFrom] = useState(isoStartOf(30));
  const [tsTo, setTsTo] = useState(isoNow());

  // tab-specific extra filters
  const [userId, setUserId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [section, setSection] = useState("");

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Aggregated audit views. CSV download mirrors what&apos;s on screen, with the same filters.
      </p>

      {/* tabs */}
      <div className="mt-6 inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
        {(
          [
            ["user", "User activity"],
            ["device", "Device activity"],
            ["secret", "Secret access"],
            ["changes", "Changes"],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`rounded px-3 py-1.5 font-medium transition ${
              tab === k
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* date + filter form */}
      <div className="mt-4 grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-4">
        <DateField label="From" value={tsFrom} onChange={setTsFrom} />
        <DateField label="To" value={tsTo} onChange={setTsTo} />

        {tab === "user" && (
          <TextField
            label="User ID (optional)"
            value={userId}
            onChange={setUserId}
            placeholder="leave blank for all"
          />
        )}
        {tab === "device" && (
          <TextField
            label="Device ID"
            value={deviceId}
            onChange={setDeviceId}
            placeholder="required"
          />
        )}
        {tab === "secret" && (
          <TextField
            label="User ID (optional)"
            value={userId}
            onChange={setUserId}
            placeholder="leave blank for all"
          />
        )}
        {tab === "changes" && (
          <TextField
            label="Section (optional)"
            value={section}
            onChange={setSection}
            placeholder="e.g. firewall.filter"
          />
        )}

        <button
          onClick={() => {
            const params: { ts_from: string; ts_to: string } & Record<string, string | undefined> = {
              ts_from: tsFrom,
              ts_to: tsTo,
            };
            if (tab === "user") params.user_id = userId || undefined;
            else if (tab === "device") params.device_id = deviceId || undefined;
            else if (tab === "secret") params.user_id = userId || undefined;
            else if (tab === "changes") params.section = section || undefined;
            const endpoint = tab === "user"
              ? "user-activity"
              : tab === "device"
                ? "device-activity"
                : tab === "secret"
                  ? "secret-access"
                  : "changes";
            void downloadReportCsv(endpoint, params, endpoint)
              .then(() => toast.success("CSV downloaded"))
              .catch((e: Error) => toast.error("Download failed", e.message));
          }}
          className="self-end rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent"
        >
          ↓ Download CSV
        </button>
      </div>

      <div className="mt-6">
        {tab === "user" && (
          <UserActivityView tsFrom={tsFrom} tsTo={tsTo} userId={userId || undefined} />
        )}
        {tab === "device" && (
          <DeviceActivityView tsFrom={tsFrom} tsTo={tsTo} deviceId={deviceId} />
        )}
        {tab === "secret" && (
          <SecretAccessView tsFrom={tsFrom} tsTo={tsTo} userId={userId || undefined} />
        )}
        {tab === "changes" && (
          <ChangeView tsFrom={tsFrom} tsTo={tsTo} section={section || undefined} />
        )}
      </div>
    </div>
  );
}

// ---------------- Form bits ----------------

function DateField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block space-y-1 text-xs font-medium text-muted-foreground">
      {label}
      <input
        type="datetime-local"
        value={toDateInput(value)}
        onChange={(e) => onChange(fromDateInput(e.target.value))}
        className={input}
      />
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block space-y-1 text-xs font-medium text-muted-foreground">
      {label}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`${input} font-mono`}
      />
    </label>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring";

// ---------------- User activity ----------------

function UserActivityView({
  tsFrom,
  tsTo,
  userId,
}: {
  tsFrom: string;
  tsTo: string;
  userId?: string;
}) {
  const { data, isLoading, error } = useQuery<UserActivityReport>({
    queryKey: ["report-user", tsFrom, tsTo, userId],
    queryFn: () => userActivityReport({ ts_from: tsFrom, ts_to: tsTo, user_id: userId }),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error)
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {(error as Error).message}
      </div>
    );
  if (!data) return null;

  return (
    <>
      <Section title="Summary (top users)">
        <Table>
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2 font-medium">User</th>
              <th className="px-3 py-2 font-medium text-right">Total</th>
              <th className="px-3 py-2 font-medium text-right">Writes</th>
              <th className="px-3 py-2 font-medium text-right">Failures</th>
              <th className="px-3 py-2 font-medium text-right">Sections</th>
              <th className="px-3 py-2 font-medium text-right">Devices</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.summary.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                  No activity in this range.
                </td>
              </tr>
            )}
            {data.summary.map((s, i) => (
              <tr key={`${s.user_id ?? "anon"}-${i}`} className="hover:bg-accent/30">
                <td className="px-3 py-2">{s.user_email ?? "(system)"}</td>
                <td className="px-3 py-2 text-right font-mono">{s.total}</td>
                <td className="px-3 py-2 text-right font-mono">{s.writes}</td>
                <td className="px-3 py-2 text-right font-mono">
                  {s.failures > 0 ? (
                    <span className="text-red-700">{s.failures}</span>
                  ) : (
                    "0"
                  )}
                </td>
                <td className="px-3 py-2 text-right font-mono">{s.sections_touched}</td>
                <td className="px-3 py-2 text-right font-mono">{s.devices_touched}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Section>

      <UserActivityEventsTable data={data} />
    </>
  );
}

function UserActivityEventsTable({ data }: { data: UserActivityReport }) {
  const cols = [
    { id: "when" },
    { id: "user" },
    { id: "section" },
    { id: "action" },
    { id: "outcome" },
    { id: "device" },
    { id: "site" },
  ];
  const { filters, onFilter, apply } = useColFilters<UserActivityReport["rows"][number]>({
    when: (r) => toLocal(r.ts),
    user: (r) => r.user_email ?? "",
    section: (r) => r.section,
    action: (r) => r.action,
    outcome: (r) => r.outcome,
    device: (r) => r.device_name ?? "",
    site: (r) =>
      [r.tenant_name, r.site_name].filter(Boolean).join(" "),
  });
  const visible = useMemo(() => apply(data.rows), [apply, data.rows]);

  return (
    <Section
      title={`Events (${visible.length}${data.truncated ? "+" : ""}${
        visible.length !== data.rows.length ? ` of ${data.rows.length}` : ""
      })`}
    >
      <Table>
        <thead className="border-b border-border bg-muted/50">
          <tr className="text-left">
            <th className="px-3 py-2 font-medium">When</th>
            <th className="px-3 py-2 font-medium">User</th>
            <th className="px-3 py-2 font-medium">Section</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">Outcome</th>
            <th className="px-3 py-2 font-medium">Device</th>
            <th className="px-3 py-2 font-medium">Tenant / Site</th>
          </tr>
          <ColumnFilterRow columns={cols} filters={filters} onFilter={onFilter} />
        </thead>
        <tbody className="divide-y divide-border">
          {visible.length === 0 && (
            <tr>
              <td colSpan={cols.length} className="px-3 py-6 text-center text-muted-foreground">
                No rows match the current filters.
              </td>
            </tr>
          )}
          {visible.map((r, i) => (
            <tr key={i} className="hover:bg-accent/30">
              <td className="px-3 py-2 font-mono text-xs">{toLocal(r.ts)}</td>
              <td className="px-3 py-2 text-xs">{r.user_email ?? "—"}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.section}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.action}</td>
              <td className="px-3 py-2 text-xs">
                <OutcomePill outcome={r.outcome} />
              </td>
              <td className="px-3 py-2 text-xs">{r.device_name ?? "—"}</td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {r.tenant_name && r.site_name
                  ? `${r.tenant_name} · ${r.site_name}`
                  : r.tenant_name ?? r.site_name ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Section>
  );
}

// ---------------- Device activity ----------------

function DeviceActivityView({
  tsFrom,
  tsTo,
  deviceId,
}: {
  tsFrom: string;
  tsTo: string;
  deviceId: string;
}) {
  const { data, isLoading, error } = useQuery<DeviceActivityReport>({
    queryKey: ["report-device", tsFrom, tsTo, deviceId],
    queryFn: () => deviceActivityReport({ ts_from: tsFrom, ts_to: tsTo, device_id: deviceId }),
    enabled: Boolean(deviceId),
  });

  if (!deviceId) {
    return (
      <p className="rounded-lg border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
        Enter a device ID to see its activity timeline.
      </p>
    );
  }
  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error)
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {(error as Error).message}
      </div>
    );
  if (!data) return null;

  return <DeviceActivityTable data={data} />;
}

function DeviceActivityTable({ data }: { data: DeviceActivityReport }) {
  const cols = [
    { id: "when" },
    { id: "user" },
    { id: "section" },
    { id: "action" },
    { id: "outcome" },
    { id: "error" },
  ];
  const { filters, onFilter, apply } = useColFilters<DeviceActivityReport["rows"][number]>({
    when: (r) => toLocal(r.ts),
    user: (r) => r.user_email ?? "",
    section: (r) => r.section,
    action: (r) => r.action,
    outcome: (r) => r.outcome,
    error: (r) => r.error_message ?? "",
  });
  const visible = useMemo(() => apply(data.rows), [apply, data.rows]);

  return (
    <Section
      title={`${data.device_name ?? data.device_id} — ${visible.length}${
        data.truncated ? "+" : ""
      }${visible.length !== data.rows.length ? ` of ${data.rows.length}` : ""} events`}
    >
      <Table>
        <thead className="border-b border-border bg-muted/50">
          <tr className="text-left">
            <th className="px-3 py-2 font-medium">When</th>
            <th className="px-3 py-2 font-medium">User</th>
            <th className="px-3 py-2 font-medium">Section</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">Outcome</th>
            <th className="px-3 py-2 font-medium">Error</th>
          </tr>
          <ColumnFilterRow columns={cols} filters={filters} onFilter={onFilter} />
        </thead>
        <tbody className="divide-y divide-border">
          {visible.length === 0 && (
            <tr>
              <td colSpan={cols.length} className="px-3 py-6 text-center text-muted-foreground">
                No rows match the current filters.
              </td>
            </tr>
          )}
          {visible.map((r, i) => (
            <tr key={i} className="hover:bg-accent/30">
              <td className="px-3 py-2 font-mono text-xs">{toLocal(r.ts)}</td>
              <td className="px-3 py-2 text-xs">{r.user_email ?? "—"}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.section}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.action}</td>
              <td className="px-3 py-2 text-xs">
                <OutcomePill outcome={r.outcome} />
              </td>
              <td className="max-w-xs truncate px-3 py-2 font-mono text-[11px] text-muted-foreground">
                {r.error_message ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Section>
  );
}

// ---------------- Secret access ----------------

function SecretAccessView({
  tsFrom,
  tsTo,
  userId,
}: {
  tsFrom: string;
  tsTo: string;
  userId?: string;
}) {
  const { data, isLoading, error } = useQuery<SecretAccessReport>({
    queryKey: ["report-secret", tsFrom, tsTo, userId],
    queryFn: () => secretAccessReport({ ts_from: tsFrom, ts_to: tsTo, user_id: userId }),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error)
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {(error as Error).message}
      </div>
    );
  if (!data) return null;

  return (
    <>
      {data.unrotated_count > 0 && (
        <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <strong>{data.unrotated_count}</strong> reveal(s) in this range have not been
          rotated since.
        </div>
      )}
      <SecretAccessTable data={data} />
    </>
  );
}

function SecretAccessTable({ data }: { data: SecretAccessReport }) {
  const cols = [
    { id: "when" },
    { id: "user" },
    { id: "device" },
    { id: "kind" },
    { id: "secret" },
    { id: "rotated" },
    { id: "justification" },
  ];
  const { filters, onFilter, apply } = useColFilters<SecretAccessReport["rows"][number]>({
    when: (r) => toLocal(r.ts),
    user: (r) => r.user_email ?? "",
    device: (r) => r.device_name ?? "",
    kind: (r) => r.secret_kind,
    secret: (r) => r.secret_label ?? r.secret_identifier,
    rotated: (r) => (r.rotated_since_reveal ? "yes" : "no"),
    justification: (r) => r.justification ?? "",
  });
  const visible = useMemo(() => apply(data.rows), [apply, data.rows]);

  return (
    <Section
      title={`Secret reveals (${visible.length}${
        visible.length !== data.rows.length ? ` of ${data.rows.length}` : ""
      })`}
    >
      <Table>
        <thead className="border-b border-border bg-muted/50">
          <tr className="text-left">
            <th className="px-3 py-2 font-medium">When</th>
            <th className="px-3 py-2 font-medium">User</th>
            <th className="px-3 py-2 font-medium">Device</th>
            <th className="px-3 py-2 font-medium">Kind</th>
            <th className="px-3 py-2 font-medium">Secret</th>
            <th className="px-3 py-2 font-medium">Rotated since?</th>
            <th className="px-3 py-2 font-medium">Justification</th>
          </tr>
          <ColumnFilterRow columns={cols} filters={filters} onFilter={onFilter} />
        </thead>
        <tbody className="divide-y divide-border">
          {visible.length === 0 && (
            <tr>
              <td colSpan={cols.length} className="px-3 py-6 text-center text-muted-foreground">
                No rows match the current filters.
              </td>
            </tr>
          )}
          {visible.map((r, i) => (
            <tr key={i} className="hover:bg-accent/30">
              <td className="px-3 py-2 font-mono text-xs">{toLocal(r.ts)}</td>
              <td className="px-3 py-2 text-xs">{r.user_email ?? "—"}</td>
              <td className="px-3 py-2 text-xs">{r.device_name ?? "—"}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.secret_kind}</td>
              <td className="px-3 py-2 font-mono text-xs">
                {r.secret_label ?? r.secret_identifier}
              </td>
              <td className="px-3 py-2 text-xs">
                {r.rotated_since_reveal ? (
                  <span className="rounded-md bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800">
                    yes — {r.last_rotation_ts ? toLocal(r.last_rotation_ts) : ""}
                  </span>
                ) : (
                  <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-900">
                    no — still leaked
                  </span>
                )}
              </td>
              <td className="max-w-xs truncate px-3 py-2 text-[11px] text-muted-foreground">
                {r.justification ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Section>
  );
}

// ---------------- Changes ----------------

function ChangeView({
  tsFrom,
  tsTo,
  section,
}: {
  tsFrom: string;
  tsTo: string;
  section?: string;
}) {
  const { data, isLoading, error } = useQuery<ChangeReport>({
    queryKey: ["report-changes", tsFrom, tsTo, section],
    queryFn: () => changeReport({ ts_from: tsFrom, ts_to: tsTo, section }),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error)
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {(error as Error).message}
      </div>
    );
  if (!data) return null;

  const bySection = Object.entries(data.by_section).sort(([, a], [, b]) => b - a);
  const byUser = Object.entries(data.by_user).sort(([, a], [, b]) => b - a);

  return (
    <>
      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <Section title="By section">
          <Table>
            <thead className="border-b border-border bg-muted/50">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">Section</th>
                <th className="px-3 py-2 font-medium text-right">Count</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {bySection.map(([s, n]) => (
                <tr key={s} className="hover:bg-accent/30">
                  <td className="px-3 py-1.5 font-mono text-xs">{s}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-xs">{n}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Section>

        <Section title="By user">
          <Table>
            <thead className="border-b border-border bg-muted/50">
              <tr className="text-left">
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium text-right">Count</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {byUser.map(([u, n]) => (
                <tr key={u} className="hover:bg-accent/30">
                  <td className="px-3 py-1.5 text-xs">{u}</td>
                  <td className="px-3 py-1.5 text-right font-mono text-xs">{n}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Section>
      </div>

      <ChangesTable data={data} />
    </>
  );
}

function ChangesTable({ data }: { data: ChangeReport }) {
  const cols = [
    { id: "when" },
    { id: "user" },
    { id: "section" },
    { id: "action" },
    { id: "device" },
    { id: "payload" },
  ];
  const { filters, onFilter, apply } = useColFilters<ChangeReport["rows"][number]>({
    when: (r) => toLocal(r.ts),
    user: (r) => r.user_email ?? "",
    section: (r) => r.section,
    action: (r) => r.action,
    device: (r) => r.device_name ?? "",
    payload: (r) => (r.request_payload ? JSON.stringify(r.request_payload) : ""),
  });
  const visible = useMemo(() => apply(data.rows), [apply, data.rows]);

  return (
    <Section
      title={`Changes (${visible.length}${data.truncated ? "+" : ""}${
        visible.length !== data.rows.length ? ` of ${data.rows.length}` : ""
      })`}
    >
      <Table>
        <thead className="border-b border-border bg-muted/50">
          <tr className="text-left">
            <th className="px-3 py-2 font-medium">When</th>
            <th className="px-3 py-2 font-medium">User</th>
            <th className="px-3 py-2 font-medium">Section</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">Device</th>
            <th className="px-3 py-2 font-medium">Payload</th>
          </tr>
          <ColumnFilterRow columns={cols} filters={filters} onFilter={onFilter} />
        </thead>
        <tbody className="divide-y divide-border">
          {visible.length === 0 && (
            <tr>
              <td colSpan={cols.length} className="px-3 py-6 text-center text-muted-foreground">
                No rows match the current filters.
              </td>
            </tr>
          )}
          {visible.map((r, i) => (
            <tr key={i} className="hover:bg-accent/30">
              <td className="px-3 py-2 font-mono text-xs">{toLocal(r.ts)}</td>
              <td className="px-3 py-2 text-xs">{r.user_email ?? "—"}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.section}</td>
              <td className="px-3 py-2 font-mono text-xs">{r.action}</td>
              <td className="px-3 py-2 text-xs">{r.device_name ?? "—"}</td>
              <td className="max-w-md truncate px-3 py-2 font-mono text-[10px] text-muted-foreground">
                {r.request_payload ? JSON.stringify(r.request_payload) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Section>
  );
}

// ---------------- shared ----------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6 first:mt-0">
      <h2 className="mb-2 text-sm font-medium text-muted-foreground">{title}</h2>
      <div className="overflow-x-auto rounded-lg border border-border bg-card">{children}</div>
    </section>
  );
}

function Table({ children }: { children: React.ReactNode }) {
  return <table className="w-full text-sm">{children}</table>;
}

// Per-column filter row. Sits directly under the <thead> labels so each
// input lines up with the column it filters. Filter values are passed
// back via `onFilter` keyed by the matching column id.
function ColumnFilterRow({
  columns,
  filters,
  onFilter,
}: {
  columns: { id: string; placeholder?: string }[];
  filters: Record<string, string>;
  onFilter: (id: string, value: string) => void;
}) {
  return (
    <tr className="border-b border-border bg-muted/20">
      {columns.map((c) => (
        <th key={c.id} className="px-2 py-1 align-top">
          <input
            value={filters[c.id] ?? ""}
            onChange={(e) => onFilter(c.id, e.target.value)}
            placeholder={c.placeholder ?? "filter…"}
            aria-label={`Filter ${c.id}`}
            className="block w-full rounded border border-input bg-background px-2 py-0.5 text-[11px] font-normal text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </th>
      ))}
    </tr>
  );
}

// Tiny hook that owns the column filter state for one table. `apply`
// runs all current filters against a row; each filter is a substring
// match against the value the accessor returns.
function useColFilters<T>(accessors: Record<string, (row: T) => string>) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const onFilter = (id: string, value: string) =>
    setFilters((prev) => ({ ...prev, [id]: value }));
  const apply = (rows: T[]) =>
    rows.filter((r) =>
      Object.entries(filters).every(([id, q]) => {
        const needle = q.trim().toLowerCase();
        if (!needle) return true;
        const acc = accessors[id];
        if (!acc) return true;
        return acc(r).toLowerCase().includes(needle);
      }),
    );
  return { filters, onFilter, apply };
}

function OutcomePill({ outcome }: { outcome: "ok" | "denied" | "failed" }) {
  const cls =
    outcome === "ok"
      ? "bg-emerald-100 text-emerald-800"
      : outcome === "denied"
        ? "bg-amber-100 text-amber-800"
        : "bg-red-100 text-red-800";
  return (
    <span className={`inline-flex rounded-md px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {outcome}
    </span>
  );
}
