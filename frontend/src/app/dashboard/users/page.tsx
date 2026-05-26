"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { createUser, listUsers, type UserListItem } from "@/lib/users";

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
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && users && users.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
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
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createUser({ email, display_name: displayName, password, is_admin: isAdmin }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }
    m.mutate();
  }

  return (
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
        <label className="space-y-1.5 md:col-span-2">
          <span className="text-sm font-medium">
            Initial password{" "}
            <span className="font-normal text-muted-foreground">(at least 12 chars)</span>
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
        <label className="flex items-center gap-2 md:col-span-2">
          <input
            type="checkbox"
            checked={isAdmin}
            onChange={(e) => setIsAdmin(e.target.checked)}
            className="size-4 rounded"
          />
          <span className="text-sm">
            Super-admin (bypasses RBAC — only for org owners)
          </span>
        </label>
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create user"}
        </button>
      </div>
    </form>
  );
}

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
