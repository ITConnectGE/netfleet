"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import { fetchUserAccessMap, type UserAccessMap } from "@/lib/access";
import {
  changeReport,
  deviceActivityReport,
  downloadReportCsv,
  secretAccessReport,
  userActivityReport,
  userRolesReport,
  type ChangeReport,
  type DeviceActivityReport,
  type SecretAccessReport,
  type UserActivityReport,
  type UserRolesReport,
} from "@/lib/reports";
import { listUsers, type UserListItem } from "@/lib/users";

type Tab = "user" | "device" | "secret" | "changes" | "user-roles" | "user-access";

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
      <div className="mt-6 inline-flex flex-wrap rounded-md border border-border bg-muted/40 p-0.5 text-xs">
        {(
          [
            ["user", "User activity"],
            ["device", "Device activity"],
            ["secret", "Secret access"],
            ["changes", "Changes"],
            ["user-roles", "User vs roles"],
            ["user-access", "User access map"],
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

      {/* date + filter form — only the audit-based tabs use it */}
      {(tab === "user" ||
        tab === "device" ||
        tab === "secret" ||
        tab === "changes") && (
      <div className="mt-4 grid gap-3 rounded-lg border border-border bg-card p-4 md:grid-cols-4">
        <DateField label="From" value={tsFrom} onChange={setTsFrom} />
        <DateField label="To" value={tsTo} onChange={setTsTo} />

        {tab === "user" && (
          <TextField
            label="User ID"
            value={userId}
            onChange={setUserId}
            example="Leave blank to include every user"
          />
        )}
        {tab === "device" && (
          <TextField
            label="Device ID"
            value={deviceId}
            onChange={setDeviceId}
            example="Required for device-scoped reports"
          />
        )}
        {tab === "secret" && (
          <TextField
            label="User ID"
            value={userId}
            onChange={setUserId}
            example="Leave blank to include every user"
          />
        )}
        {tab === "changes" && (
          <TextField
            label="Section"
            value={section}
            onChange={setSection}
            placeholder="firewall.filter"
            example="Optional · matches the audit section identifier"
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
      )}

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
        {tab === "user-roles" && <UserRolesView />}
        {tab === "user-access" && <UserAccessView />}
      </div>
    </div>
  );
}

// ---------------- User vs roles (P21 #15.7) ----------------

function UserRolesView() {
  const { data, isLoading, error } = useQuery<UserRolesReport>({
    queryKey: ["report", "user-roles"],
    queryFn: userRolesReport,
  });

  const [userFilter, setUserFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("");

  const filteredUsers = useMemo(() => {
    if (!data) return [];
    const needle = userFilter.trim().toLowerCase();
    return data.users.filter((u) => {
      if (
        needle &&
        !(u.email.toLowerCase().includes(needle) ||
          (u.display_name ?? "").toLowerCase().includes(needle))
      ) {
        return false;
      }
      if (roleFilter && !u.assignments.some((a) => a.role_id === roleFilter)) {
        return false;
      }
      return true;
    });
  }, [data, userFilter, roleFilter]);

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error)
    return (
      <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {(error as Error).message}
      </p>
    );
  if (!data) return null;

  return (
    <div className="space-y-6">
      <section>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Users</h2>
          <div className="flex gap-2">
            <input
              type="search"
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
              placeholder="Filter by name or email…"
              className={input}
            />
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className={input}
            >
              <option value="">All roles</option>
              {data.roles.map((r) => (
                <option key={r.role_id} value={r.role_id}>
                  {r.role_name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {filteredUsers.length} of {data.users.length} user
          {data.users.length === 1 ? "" : "s"}
        </p>
        <div className="mt-3 overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">User</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">MFA</th>
                <th className="px-3 py-2 font-medium">Roles</th>
                <th className="px-3 py-2 font-medium text-right">Permissions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredUsers.map((u) => (
                <tr key={u.user_id} className="align-top hover:bg-accent/30">
                  <td className="px-3 py-2">
                    <div className="font-medium">{u.display_name ?? u.email}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {u.email}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {u.is_admin && (
                      <span className="mr-1 rounded-md bg-primary/10 px-1.5 py-0.5 font-medium text-primary">
                        admin
                      </span>
                    )}
                    {u.is_active ? "active" : "disabled"}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {u.totp_enrolled && (
                      <span className="mr-1 rounded-md bg-emerald-100 px-1.5 py-0.5 text-emerald-800">
                        TOTP
                      </span>
                    )}
                    {u.otp_login_enabled && (
                      <span className="rounded-md bg-sky-100 px-1.5 py-0.5 text-sky-800">
                        OTP
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {u.assignments.length === 0 ? (
                      <span className="text-xs italic text-muted-foreground">
                        no roles
                      </span>
                    ) : (
                      <ul className="space-y-0.5 text-xs">
                        {u.assignments.map((a, i) => (
                          <li key={i}>
                            <span className="font-mono">{a.role_name}</span>{" "}
                            <span className="text-muted-foreground">
                              · {a.scope_type}
                              {a.scope_label && a.scope_type !== "organization"
                                ? ` · ${a.scope_label}`
                                : ""}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right text-xs text-muted-foreground">
                    {u.permission_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-base font-semibold">Role catalogue</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Side-by-side comparison. Common permissions across roles share row
          labels — scan vertically to spot drift between similar roles.
        </p>
        <div className="mt-3 overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2 font-medium">Users</th>
                <th className="px-3 py-2 font-medium">Permissions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.roles.map((r) => (
                <tr key={r.role_id} className="align-top hover:bg-accent/30">
                  <td className="px-3 py-2">
                    <div className="font-medium">{r.role_name}</div>
                    {r.is_system && (
                      <span className="mt-1 inline-block rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        system
                      </span>
                    )}
                    {r.description && (
                      <div className="mt-1 text-[11px] text-muted-foreground">
                        {r.description}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs">{r.user_count}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {r.permissions.map((p) => (
                        <span
                          key={p}
                          className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10px]"
                        >
                          {p}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// ---------------- User access map (P21 #15.8) ----------------

function UserAccessView() {
  const { data: users } = useQuery<UserListItem[]>({
    queryKey: ["users"],
    queryFn: listUsers,
  });
  const [pickedUserId, setPickedUserId] = useState<string>("");
  const picked = users?.find((u) => u.id === pickedUserId);

  const { data: map, isLoading } = useQuery<UserAccessMap>({
    queryKey: ["user-access", pickedUserId],
    queryFn: () => fetchUserAccessMap(pickedUserId),
    enabled: Boolean(pickedUserId),
  });

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs font-medium text-muted-foreground">
          User
          <select
            value={pickedUserId}
            onChange={(e) => setPickedUserId(e.target.value)}
            className={`${input} ml-2`}
          >
            <option value="">— pick a user —</option>
            {(users ?? []).map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name ?? u.email}
              </option>
            ))}
          </select>
        </label>
        {picked && (
          <span className="text-xs text-muted-foreground">{picked.email}</span>
        )}
      </div>

      {!pickedUserId && (
        <p className="mt-6 rounded-md border border-dashed border-border bg-card p-6 text-center text-sm text-muted-foreground">
          Pick a user above to see every tenant, site and device they can
          reach, with the inheritance chain that grants it.
        </p>
      )}

      {pickedUserId && isLoading && (
        <p className="mt-4 text-sm text-muted-foreground">Loading…</p>
      )}

      {map && (
        <>
          <section className="mt-6">
            <h3 className="text-sm font-medium text-muted-foreground">
              Effective permissions
            </h3>
            {map.permissions.length === 0 ? (
              <p className="mt-2 text-xs italic text-muted-foreground">
                None — this user has no role assignments.
              </p>
            ) : (
              <div className="mt-2 flex flex-wrap gap-1">
                {map.permissions.map((p, i) => (
                  <span
                    key={i}
                    className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10px]"
                  >
                    {p.section === "*" && p.action === "*"
                      ? "* (super-admin)"
                      : `${p.section}:${p.action}`}
                  </span>
                ))}
              </div>
            )}
          </section>

          <section className="mt-6">
            <h3 className="text-sm font-medium text-muted-foreground">
              Reachable scopes
            </h3>
            {map.tenants.length === 0 ? (
              <p className="mt-2 text-xs italic text-muted-foreground">
                None.
              </p>
            ) : (
              <div className="mt-3 space-y-3">
                {map.tenants.map((t) => (
                  <div
                    key={t.tenant_id}
                    className="rounded-lg border border-border bg-card p-4"
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <div className="font-semibold">{t.tenant_name}</div>
                      <span className="text-[11px] text-muted-foreground">
                        tenant
                      </span>
                    </div>
                    <GrantChips grants={t.grants} />

                    {t.sites.length > 0 && (
                      <ul className="mt-3 space-y-2 border-l border-border pl-3">
                        {t.sites.map((s) => (
                          <li key={s.site_id}>
                            <div className="flex items-baseline justify-between gap-3">
                              <div className="text-sm">{s.site_name}</div>
                              <span className="text-[11px] text-muted-foreground">
                                site
                              </span>
                            </div>
                            <GrantChips grants={s.grants} />
                            {s.devices.length > 0 && (
                              <ul className="mt-2 space-y-1 border-l border-border pl-3">
                                {s.devices.map((d) => (
                                  <li key={d.device_id}>
                                    <div className="flex items-baseline justify-between gap-3">
                                      <div className="font-mono text-xs">
                                        {d.device_name}
                                      </div>
                                      <span className="text-[10px] text-muted-foreground">
                                        device
                                      </span>
                                    </div>
                                    <GrantChips grants={d.grants} />
                                  </li>
                                ))}
                              </ul>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function GrantChips({
  grants,
}: {
  grants: UserAccessMap["tenants"][number]["grants"];
}) {
  if (grants.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {grants.map((g, i) => (
        <span
          key={i}
          className="rounded-md bg-muted px-1.5 py-0.5 text-[10px]"
          title={
            g.via_scope_type
              ? `via ${g.via_scope_type}${g.via_scope_label ? ` · ${g.via_scope_label}` : ""}`
              : "via super-admin"
          }
        >
          {g.role_name ?? "super-admin"}{" "}
          <span className="text-muted-foreground">
            ({g.via_scope_type ?? "*"})
          </span>
        </span>
      ))}
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
  example,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  example?: string;
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
      {example && (
        <span className="block text-[11px] italic font-normal normal-case text-muted-foreground">
          {example}
        </span>
      )}
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
