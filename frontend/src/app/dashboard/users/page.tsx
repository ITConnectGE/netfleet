"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";

import { Field } from "@/components/form-field";
import { useToast } from "@/components/toast";
import { listRoles, type Role } from "@/lib/roles";
import {
  createUser,
  listUsers,
  type UserInviteResponse,
  type UserListItem,
} from "@/lib/users";

export default function UsersPage() {
  const qc = useQueryClient();
  const { data: users, isLoading } = useQuery<UserListItem[]>({
    queryKey: ["users"],
    queryFn: listUsers,
  });
  const [showForm, setShowForm] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Invite IT support staff and assign them granular roles per site or device.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ Invite user"}
        </button>
      </div>

      {showForm && (
        <UserForm
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["users"] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Email</th>
              <th className="px-4 py-2.5 font-medium">Mobile</th>
              <th className="px-4 py-2.5 font-medium">Auth</th>
              <th className="px-4 py-2.5 font-medium">MFA</th>
              <th className="px-4 py-2.5 font-medium">Roles</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium">Last login</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && users && users.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                  No users yet.
                </td>
              </tr>
            )}
            {users?.map((u) => (
              <tr key={u.id} className="hover:bg-accent/30">
                <td className="px-4 py-3">
                  <Link
                    href={`/dashboard/users/${u.id}`}
                    className="font-medium hover:underline"
                  >
                    {u.display_name ?? "—"}
                  </Link>
                  {u.is_admin && (
                    <span className="ml-2 rounded-md bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
                      admin
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                  {u.mobile_phone ?? "—"}
                </td>
                <td className="px-4 py-3 text-xs">{u.auth_method}</td>
                <td className="px-4 py-3">
                  {u.totp_enrolled ? (
                    <span className="text-emerald-600">✓</span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-4 py-3">{u.assignment_count}</td>
                <td className="px-4 py-3">
                  {u.is_active ? (
                    <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">
                      active
                    </span>
                  ) : (
                    <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-800">
                      disabled
                    </span>
                  )}
                  {u.must_change_password && (
                    <span className="ml-2 rounded-md bg-amber-100 px-2 py-0.5 text-[10px] text-amber-900">
                      must change pwd
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "never"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UserForm({ onCreated }: { onCreated: () => void }) {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [mobile, setMobile] = useState("");
  // Auto-generate is the new default — admins shouldn't know an active
  // password long-term, so flipping to manual is an opt-in.
  const [autoGenerate, setAutoGenerate] = useState(true);
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [roleIds, setRoleIds] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);
  const [generated, setGenerated] = useState<{
    password: string;
    email: string;
    emailSent: boolean;
  } | null>(null);

  const { data: roles } = useQuery<Role[]>({
    queryKey: ["roles"],
    queryFn: listRoles,
  });
  const visibleRoles = useMemo(
    () => (roles ?? []).sort((a, b) => a.name.localeCompare(b.name)),
    [roles],
  );

  const m = useMutation<UserInviteResponse>({
    mutationFn: () =>
      createUser({
        email,
        display_name: displayName,
        password: autoGenerate ? null : password,
        mobile_phone: mobile.trim() || null,
        is_admin: isAdmin,
        role_ids: Array.from(roleIds),
      }),
    onSuccess: (res) => {
      // Three outcomes:
      //   - email delivered → simple toast, invitee got the creds inline
      //   - generated password but email failed → modal so the inviter
      //     can still hand the password off out of band
      //   - inviter typed the password themselves → nothing to surface
      if (res.email_sent) {
        toast.success("Invite emailed", email);
        onCreated();
      } else if (res.generated_password) {
        setGenerated({
          password: res.generated_password,
          email,
          emailSent: false,
        });
      } else {
        toast.success("User created", email);
        onCreated();
      }
    },
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!autoGenerate && password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }
    m.mutate();
  }

  function toggleRole(id: string, on: boolean) {
    setRoleIds((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  return (
    <>
      <form onSubmit={onSubmit} className="mt-6 rounded-lg border border-border bg-card p-5">
        {error && (
          <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Display name</span>
            <input
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className={inputClass}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              autoComplete="off"
            />
          </label>
          <Field
            label="Mobile phone"
            example="Optional · used for SMS one-time codes at login"
          >
            <input
              type="tel"
              value={mobile}
              onChange={(e) => setMobile(e.target.value)}
              className={`${inputClass} font-mono`}
              placeholder="+995 555 12 34 56"
            />
          </Field>
          <label className="flex items-center gap-2 self-end pb-2">
            <input
              type="checkbox"
              checked={isAdmin}
              onChange={(e) => setIsAdmin(e.target.checked)}
              className="size-4 rounded"
            />
            <span className="text-sm">
              Super-admin{" "}
              <span className="text-xs text-muted-foreground">
                (bypasses RBAC — only for org owners)
              </span>
            </span>
          </label>
        </div>

        <div className="mt-5 rounded-md border border-border bg-muted/30 p-4">
          <label className="flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={autoGenerate}
              onChange={(e) => setAutoGenerate(e.target.checked)}
              className="size-4 rounded"
            />
            Generate a strong password
            <span className="text-xs font-normal text-muted-foreground">
              (shown once; user must change it on first login)
            </span>
          </label>
          {!autoGenerate && (
            <label className="mt-3 block space-y-1.5">
              <span className="text-sm font-medium">
                Initial password{" "}
                <span className="font-normal text-muted-foreground">
                  (at least 12 chars)
                </span>
              </span>
              <input
                type="password"
                required
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClass}
                autoComplete="new-password"
              />
            </label>
          )}
        </div>

        <div className="mt-5">
          <div className="text-sm font-medium">Roles</div>
          <p className="text-xs text-muted-foreground">
            Assigned at organisation scope. Site- and device-specific
            scopes can be added on the user&apos;s detail page after creation.
          </p>
          {visibleRoles.length === 0 ? (
            <p className="mt-2 text-xs italic text-muted-foreground">
              No roles defined yet — create some under Settings → Access control.
            </p>
          ) : (
            <ul className="mt-2 grid gap-1 md:grid-cols-2">
              {visibleRoles.map((r) => (
                <li key={r.id}>
                  <label className="flex items-start gap-2 rounded-md border border-border bg-background px-2 py-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={roleIds.has(r.id)}
                      onChange={(e) => toggleRole(r.id, e.target.checked)}
                      className="mt-0.5 size-4 rounded"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block font-medium">{r.name}</span>
                      {r.description && (
                        <span className="block text-[11px] text-muted-foreground">
                          {r.description}
                        </span>
                      )}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="submit"
            disabled={m.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Inviting…" : "Invite user"}
          </button>
        </div>
      </form>

      {generated && (
        <GeneratedPasswordModal
          email={generated.email}
          password={generated.password}
          emailSent={generated.emailSent}
          onClose={() => {
            setGenerated(null);
            onCreated();
          }}
        />
      )}
    </>
  );
}

function GeneratedPasswordModal({
  email,
  password,
  emailSent,
  onClose,
}: {
  email: string;
  password: string;
  emailSent: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl">
        <h3 className="text-lg font-semibold">User invited</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {emailSent ? (
            <>
              An invite email with sign-in details has been delivered to{" "}
              <span className="font-mono">{email}</span>.
            </>
          ) : (
            <>
              SMTP is unavailable — hand this password to{" "}
              <span className="font-mono">{email}</span> through a channel
              they trust. NetFleet will not show it again; they will be
              forced to change it on first sign-in.
            </>
          )}
        </p>
        <div className="mt-4 flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2 font-mono text-sm">
          <span className="flex-1 select-all break-all">{password}</span>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(password).then(
                () => toast.success("Password copied"),
                () => toast.error("Copy failed"),
              );
            }}
            className="rounded-md border border-input bg-card px-2 py-1 text-xs font-medium hover:bg-accent"
          >
            Copy
          </button>
        </div>
        {!emailSent && (
          <div className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Once you close this dialog the plaintext is gone — only the
            hash stays on the server. Configure SMTP in Settings to have
            future invites delivered automatically.
          </div>
        )}
        <div className="mt-5 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            {emailSent ? "Done" : "I’ve copied it"}
          </button>
        </div>
      </div>
    </div>
  );
}

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
