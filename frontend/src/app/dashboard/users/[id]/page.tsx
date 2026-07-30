"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { RiskReportCard } from "@/components/risk-report-card";
import { useToast } from "@/components/toast";
import { fetchMe } from "@/lib/auth";
import { listDevices, type Device } from "@/lib/devices";
import { listRoles, type Role } from "@/lib/roles";
import { listSites, type Site } from "@/lib/sites";
import { listTenants, type Tenant } from "@/lib/tenants";
import {
  bulkCreateAssignments,
  deleteAssignment,
  listAssignments,
  listUsers,
  resetUserPassword,
  updateUser,
  type Assignment,
  type AssignmentBulkScope,
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

  const toast = useToast();
  // The server refuses self-demotion too; knowing who we are lets the
  // button explain itself instead of failing after the click.
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const isSelf = me?.id === id;

  const toggleActive = useMutation({
    mutationFn: (active: boolean) => updateUser(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
    onError: (e: Error) => toast.error("Could not update user", e.message),
  });

  const toggleAdmin = useMutation({
    mutationFn: (admin: boolean) => updateUser(id, { is_admin: admin }),
    onSuccess: (_r, admin) => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["user", id] });
      toast.success(
        admin ? "Super-admin granted" : "Super-admin revoked",
        admin
          ? "This user now has full access to everything in the organisation."
          : "Access is now limited to the roles assigned below.",
      );
    },
    // The server refuses to remove the last admin; surface its reason
    // rather than a generic failure.
    onError: (e: Error) => toast.error("Could not change super-admin", e.message),
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
          {/* Super-admin is a flag, not a role, so the role table below
              cannot express it — without this control there was no way to
              promote or demote anyone from the UI at all. */}
          <button
            onClick={() => toggleAdmin.mutate(!user.is_admin)}
            disabled={toggleAdmin.isPending || isSelf}
            title={
              isSelf
                ? "You cannot change your own super-admin rights"
                : user.is_admin
                  ? "Remove super-admin rights, leaving only the roles assigned below"
                  : "Grant full access to everything in this organisation"
            }
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm transition hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            {user.is_admin ? "Revoke super-admin" : "Make super-admin"}
          </button>
          <button
            onClick={() => toggleActive.mutate(!user.is_active)}
            disabled={toggleActive.isPending || isSelf}
            title={isSelf ? "You cannot disable your own account" : undefined}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm transition hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            {user.is_active ? "Disable user" : "Enable user"}
          </button>
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
              assignments.map((a) => {
                const expired =
                  a.expires_at && new Date(a.expires_at).getTime() <= Date.now();
                return (
                  <tr key={a.id} className="hover:bg-accent/30">
                    <td className="px-4 py-2.5 font-medium">{a.role_name}</td>
                    <td className="px-4 py-2.5">
                      <span className="font-mono text-xs">{a.scope_type}</span>
                      {a.scope_label && (
                        <span className="ml-2 text-muted-foreground">
                          · {a.scope_label}
                        </span>
                      )}
                      {a.expires_at && (
                        <span
                          className={`ml-2 rounded-md px-1.5 py-0.5 text-[10px] ${
                            expired
                              ? "bg-red-100 text-red-900"
                              : "bg-amber-100 text-amber-900"
                          }`}
                          title={`Expires ${new Date(a.expires_at).toLocaleString()}`}
                        >
                          {expired ? "expired" : "expires"}{" "}
                          {new Date(a.expires_at).toLocaleString()}
                        </span>
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
                );
              })
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
  const toast = useToast();
  const [roleId, setRoleId] = useState(roles[0]?.id ?? "");
  const [mode, setMode] = useState<"organization" | "scoped">("organization");
  const [tenantPicks, setTenantPicks] = useState<Set<string>>(new Set());
  const [sitePicks, setSitePicks] = useState<Set<string>>(new Set());
  const [devicePicks, setDevicePicks] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const tree = useMemo(() => {
    const sitesByTenant = new Map<string, Site[]>();
    for (const s of sites) {
      const arr = sitesByTenant.get(s.tenant_id) ?? [];
      arr.push(s);
      sitesByTenant.set(s.tenant_id, arr);
    }
    const devicesBySite = new Map<string, Device[]>();
    for (const d of devices) {
      const arr = devicesBySite.get(d.site_id) ?? [];
      arr.push(d);
      devicesBySite.set(d.site_id, arr);
    }
    return [...tenants]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((t) => ({
        tenant: t,
        sites: (sitesByTenant.get(t.id) ?? [])
          .sort((a, b) => a.name.localeCompare(b.name))
          .map((s) => ({
            site: s,
            devices: (devicesBySite.get(s.id) ?? []).sort((a, b) =>
              a.name.localeCompare(b.name),
            ),
          })),
      }));
  }, [tenants, sites, devices]);

  const { coalescedScopes, totalChildrenCovered } = useMemo(() => {
    // Coalesce: when a tenant is ticked, don't bother sending its
    // sites/devices as separate assignments — the inheritance walker
    // covers them. Same logic one level down for sites vs their
    // devices. Keeps the role_assignments row count proportional to
    // intent rather than to fleet size.
    const scopes: AssignmentBulkScope[] = [];
    let covered = 0;
    for (const tn of tree) {
      if (tenantPicks.has(tn.tenant.id)) {
        scopes.push({ scope_type: "tenant", scope_id: tn.tenant.id });
        covered +=
          tn.sites.length + tn.sites.reduce((a, s) => a + s.devices.length, 0);
        continue;
      }
      for (const sn of tn.sites) {
        if (sitePicks.has(sn.site.id)) {
          scopes.push({ scope_type: "site", scope_id: sn.site.id });
          covered += sn.devices.length;
          continue;
        }
        for (const d of sn.devices) {
          if (devicePicks.has(d.id)) {
            scopes.push({ scope_type: "device", scope_id: d.id });
          }
        }
      }
    }
    return { coalescedScopes: scopes, totalChildrenCovered: covered };
  }, [tree, tenantPicks, sitePicks, devicePicks]);

  function resetPicks() {
    setTenantPicks(new Set());
    setSitePicks(new Set());
    setDevicePicks(new Set());
  }

  const m = useMutation({
    mutationFn: () =>
      bulkCreateAssignments(userId, {
        role_id: roleId,
        scopes:
          mode === "organization"
            ? [{ scope_type: "organization", scope_id: null }]
            : coalescedScopes,
      }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["assignments", userId] });
      qc.invalidateQueries({ queryKey: ["users"] });
      setError(null);
      resetPicks();
      const skipped =
        res.skipped_existing > 0
          ? ` · ${res.skipped_existing} already existed`
          : "";
      toast.success(
        `Granted ${res.created} assignment${res.created === 1 ? "" : "s"}`,
        skipped || undefined,
      );
    },
    onError: (e: Error) => setError(e.message),
  });

  function toggle<T>(set: Set<T>, val: T, on: boolean): Set<T> {
    const next = new Set(set);
    if (on) next.add(val);
    else next.delete(val);
    return next;
  }

  const canSubmit =
    !!roleId &&
    (mode === "organization" || coalescedScopes.length > 0) &&
    !m.isPending;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!canSubmit) return;
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

      <div className="mt-3 grid gap-3 md:grid-cols-2">
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
        <fieldset className="space-y-1 text-xs font-medium text-muted-foreground">
          <legend>Scope</legend>
          <div className="flex gap-3 text-sm font-normal text-foreground">
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                checked={mode === "organization"}
                onChange={() => setMode("organization")}
              />
              Organization-wide
            </label>
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                checked={mode === "scoped"}
                onChange={() => setMode("scoped")}
              />
              Specific tenants / sites / devices
            </label>
          </div>
        </fieldset>
      </div>

      {mode === "scoped" && (
        <div className="mt-4">
          <div className="mb-1 text-xs text-muted-foreground">
            Tick anywhere in the tree. A tenant tick covers its sites and
            devices automatically (inheritance) — children stay unchecked
            unless you want a separate, narrower grant.
          </div>
          {tree.length === 0 ? (
            <p className="rounded-md border border-dashed border-border bg-card p-4 text-center text-xs text-muted-foreground">
              No tenants yet.
            </p>
          ) : (
            <div className="max-h-80 overflow-y-auto rounded-md border border-border bg-background p-2">
              {tree.map((tn) => {
                const tenantTicked = tenantPicks.has(tn.tenant.id);
                return (
                  <div key={tn.tenant.id} className="text-sm">
                    <label className="flex items-center gap-2 rounded px-2 py-1 hover:bg-accent/40">
                      <input
                        type="checkbox"
                        checked={tenantTicked}
                        onChange={(e) =>
                          setTenantPicks((s) =>
                            toggle(s, tn.tenant.id, e.target.checked),
                          )
                        }
                        className="size-4"
                      />
                      <span className="font-medium">{tn.tenant.name}</span>
                      <span className="text-[11px] text-muted-foreground">
                        tenant
                      </span>
                    </label>
                    {!tenantTicked &&
                      tn.sites.map((sn) => {
                        const siteTicked = sitePicks.has(sn.site.id);
                        return (
                          <div key={sn.site.id} className="ml-6">
                            <label className="flex items-center gap-2 rounded px-2 py-1 hover:bg-accent/40">
                              <input
                                type="checkbox"
                                checked={siteTicked}
                                onChange={(e) =>
                                  setSitePicks((s) =>
                                    toggle(s, sn.site.id, e.target.checked),
                                  )
                                }
                                className="size-4"
                              />
                              <span>{sn.site.name}</span>
                              <span className="text-[11px] text-muted-foreground">
                                site
                              </span>
                            </label>
                            {!siteTicked &&
                              sn.devices.map((d) => (
                                <label
                                  key={d.id}
                                  className="ml-6 flex items-center gap-2 rounded px-2 py-1 hover:bg-accent/40"
                                >
                                  <input
                                    type="checkbox"
                                    checked={devicePicks.has(d.id)}
                                    onChange={(e) =>
                                      setDevicePicks((s) =>
                                        toggle(s, d.id, e.target.checked),
                                      )
                                    }
                                    className="size-4"
                                  />
                                  <span className="font-mono text-xs">
                                    {d.name}
                                  </span>
                                  <span className="text-[10px] text-muted-foreground">
                                    device
                                  </span>
                                </label>
                              ))}
                          </div>
                        );
                      })}
                  </div>
                );
              })}
            </div>
          )}
          <p className="mt-2 text-[11px] text-muted-foreground">
            {coalescedScopes.length} explicit grant
            {coalescedScopes.length === 1 ? "" : "s"} · {totalChildrenCovered}{" "}
            child scope{totalChildrenCovered === 1 ? "" : "s"} inherited
          </p>
        </div>
      )}

      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending
            ? "Granting…"
            : mode === "organization"
              ? "Grant organization-wide"
              : `Grant ${coalescedScopes.length} scope${coalescedScopes.length === 1 ? "" : "s"}`}
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
