"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { RiskReportCard } from "@/components/risk-report-card";
import { listDevices, type Device } from "@/lib/devices";
import { listRoles, type Role } from "@/lib/roles";
import { listSites, type Site } from "@/lib/sites";
import { listTenants, type Tenant } from "@/lib/tenants";
import {
  createAssignment,
  deleteAssignment,
  listAssignments,
  listUsers,
  resetUserPassword,
  updateUser,
  type Assignment,
  type UserListItem,
} from "@/lib/users";

export default function UserDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const qc = useQueryClient();

  const { data: users } = useQuery<UserListItem[]>({
    queryKey: ["users"],
    queryFn: listUsers,
  });
  const user = users?.find((u) => u.id === id);

  const { data: assignments } = useQuery<Assignment[]>({
    queryKey: ["assignments", id],
    queryFn: () => listAssignments(id),
    enabled: Boolean(id),
  });
  const { data: roles } = useQuery<Role[]>({ queryKey: ["roles"], queryFn: listRoles });
  const { data: tenants } = useQuery<Tenant[]>({
    queryKey: ["tenants"],
    queryFn: listTenants,
  });
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: () => listSites(),
  });
  const { data: devices } = useQuery<Device[]>({
    queryKey: ["devices"],
    queryFn: () => listDevices(),
  });

  const toggleActive = useMutation({
    mutationFn: (active: boolean) => updateUser(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const deleteAssignmentMut = useMutation({
    mutationFn: (aid: string) => deleteAssignment(id, aid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["assignments", id] }),
  });

  if (!user) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div>
      <Link href="/dashboard/users" className="text-xs text-muted-foreground hover:underline">
        ← Users
      </Link>
      <div className="mt-1 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {user.display_name ?? user.email}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {user.email} · {user.auth_method} ·{" "}
            {user.is_admin ? "super-admin" : "standard user"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!user.is_admin && (
            <button
              onClick={() => toggleActive.mutate(!user.is_active)}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm transition hover:bg-accent"
            >
              {user.is_active ? "Disable user" : "Enable user"}
            </button>
          )}
        </div>
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <ResetPasswordCard userId={id} />
        <UserMetaCard user={user} />
      </div>

      <h2 className="mt-10 text-lg font-semibold">Role assignments</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Each row grants the user one role within the chosen scope (org / site / device).
      </p>

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Role</th>
              <th className="px-4 py-2.5 font-medium">Scope</th>
              <th className="px-4 py-2.5 font-medium">Created</th>
              <th className="px-4 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {!assignments || assignments.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-muted-foreground">
                  No assignments. Use the form below to add one.
                </td>
              </tr>
            ) : (
              assignments.map((a) => (
                <tr key={a.id} className="hover:bg-accent/30">
                  <td className="px-4 py-2.5 font-medium">{a.role_name}</td>
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-xs">{a.scope_type}</span>
                    {a.scope_label && (
                      <span className="ml-2 text-muted-foreground">· {a.scope_label}</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => {
                        if (confirm(`Revoke "${a.role_name}" from this user?`)) {
                          deleteAssignmentMut.mutate(a.id);
                        }
                      }}
                      className="text-xs text-destructive hover:underline"
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {roles && tenants && sites && devices && (
        <AssignForm
          userId={id}
          roles={roles}
          tenants={tenants}
          sites={sites}
          devices={devices}
        />
      )}

      <RiskReportCard userId={id} />
    </div>
  );
}

function UserMetaCard({ user }: { user: UserListItem }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <h3 className="text-sm font-medium text-muted-foreground">User</h3>
      <dl className="mt-3 space-y-2 text-sm">
        <Row label="Status">
          {user.is_active ? (
            <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">
              active
            </span>
          ) : (
            <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-800">
              disabled
            </span>
          )}
        </Row>
        <Row label="MFA">{user.totp_enrolled ? "TOTP enrolled" : "not enrolled"}</Row>
        <Row label="Last login">
          {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "never"}
        </Row>
        <Row label="Created">{new Date(user.created_at).toLocaleString()}</Row>
      </dl>
    </div>
  );
}

function ResetPasswordCard({ userId }: { userId: string }) {
  const [pw, setPw] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => resetUserPassword(userId, pw),
    onSuccess: () => {
      setDone(true);
      setPw("");
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <h3 className="text-sm font-medium text-muted-foreground">Reset password</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Issue a new password the user must use to sign in.
      </p>
      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}
      {done && (
        <div className="mt-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
          Password updated.
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          setDone(false);
          if (pw.length < 12) {
            setError("Password must be at least 12 characters.");
            return;
          }
          m.mutate();
        }}
        className="mt-3 flex gap-2"
      >
        <input
          type="password"
          required
          minLength={12}
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          placeholder="new password ≥ 12 chars"
          className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          Reset
        </button>
      </form>
    </div>
  );
}

function AssignForm({
  userId,
  roles,
  tenants,
  sites,
  devices,
}: {
  userId: string;
  roles: Role[];
  tenants: Tenant[];
  sites: Site[];
  devices: Device[];
}) {
  const qc = useQueryClient();
  const [roleId, setRoleId] = useState(roles[0]?.id ?? "");
  const [scopeType, setScopeType] = useState<
    "organization" | "tenant" | "site" | "device"
  >("organization");
  const [scopeId, setScopeId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createAssignment(userId, {
        role_id: roleId,
        scope_type: scopeType,
        scope_id: scopeType === "organization" ? null : scopeId || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["assignments", userId] });
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });

  const scopeOptions =
    scopeType === "tenant"
      ? tenants.map((t) => ({ value: t.id, label: t.name }))
      : scopeType === "site"
        ? sites.map((s) => ({
            value: s.id,
            label: `${s.tenant_name ? `${s.tenant_name} · ` : ""}${s.name}`,
          }))
        : scopeType === "device"
          ? devices.map((d) => ({ value: d.id, label: d.name }))
          : [];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
      className="mt-6 rounded-lg border border-border bg-card p-5"
    >
      <h3 className="text-sm font-medium">Add assignment</h3>
      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="mt-3 grid gap-3 md:grid-cols-4">
        <label className="space-y-1 text-xs font-medium text-muted-foreground">
          Role
          <select
            value={roleId}
            onChange={(e) => setRoleId(e.target.value)}
            className={selectClass}
          >
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs font-medium text-muted-foreground">
          Scope
          <select
            value={scopeType}
            onChange={(e) => {
              const v = e.target.value as "organization" | "tenant" | "site" | "device";
              setScopeType(v);
              setScopeId("");
            }}
            className={selectClass}
          >
            <option value="organization">organization (all)</option>
            <option value="tenant">tenant</option>
            <option value="site">site</option>
            <option value="device">device</option>
          </select>
        </label>
        {scopeType !== "organization" && (
          <label className="space-y-1 text-xs font-medium text-muted-foreground md:col-span-2">
            {scopeType === "tenant"
              ? "Tenant"
              : scopeType === "site"
                ? "Site"
                : "Device"}
            <select
              required
              value={scopeId}
              onChange={(e) => setScopeId(e.target.value)}
              className={selectClass}
            >
              <option value="">— pick one —</option>
              {scopeOptions.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending || !roleId || (scopeType !== "organization" && !scopeId)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Adding…" : "Add assignment"}
        </button>
      </div>
    </form>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

const selectClass =
  "block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring";
