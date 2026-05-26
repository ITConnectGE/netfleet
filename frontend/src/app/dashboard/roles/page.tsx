"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import {
  createRole,
  deleteRole,
  listRoles,
  listSections,
  type PermissionAction,
  type Role,
  type SectionInfo,
} from "@/lib/roles";

export default function RolesPage() {
  const qc = useQueryClient();
  const { data: roles, isLoading } = useQuery<Role[]>({
    queryKey: ["roles"],
    queryFn: listRoles,
  });
  const { data: sections } = useQuery<SectionInfo[]>({
    queryKey: ["sections"],
    queryFn: listSections,
  });
  const [showForm, setShowForm] = useState(false);

  const del = useMutation({
    mutationFn: (id: string) => deleteRole(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Roles</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Bundles of permissions you can assign to IT support staff with site- or device-level scope.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New role"}
        </button>
      </div>

      {showForm && sections && (
        <RoleForm
          sections={sections}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["roles"] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {roles?.map((r) => (
          <div key={r.id} className="rounded-lg border border-border bg-card p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-medium">{r.name}</h3>
                  {r.is_system && (
                    <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                      system
                    </span>
                  )}
                </div>
                {r.description && (
                  <p className="mt-1 text-xs text-muted-foreground">{r.description}</p>
                )}
              </div>
              {!r.is_system && (
                <button
                  onClick={() => {
                    if (confirm(`Delete role "${r.name}"?`)) del.mutate(r.id);
                  }}
                  className="text-xs text-destructive hover:underline"
                >
                  Delete
                </button>
              )}
            </div>
            <div className="mt-3 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                {r.permissions.length} permission{r.permissions.length === 1 ? "" : "s"}
              </span>
              <span className="text-muted-foreground">
                {r.assignment_count} assignment{r.assignment_count === 1 ? "" : "s"}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-1">
              {r.permissions.slice(0, 6).map((p) => (
                <span
                  key={p.id}
                  className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[10px]"
                >
                  {p.section}:{p.action}
                </span>
              ))}
              {r.permissions.length > 6 && (
                <span className="text-[10px] text-muted-foreground">
                  + {r.permissions.length - 6} more
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RoleForm({
  sections,
  onCreated,
}: {
  sections: SectionInfo[];
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  // Set<`${section}:${action}`>
  const [grants, setGrants] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const grouped = useMemo(() => {
    return {
      app: sections.filter((s) => s.kind === "app"),
      driver: sections.filter((s) => s.kind === "driver"),
    };
  }, [sections]);

  const m = useMutation({
    mutationFn: () =>
      createRole({
        name,
        description: description || null,
        permissions: Array.from(grants).map((g) => {
          const [section, action] = g.split(":");
          return { section, action: action as PermissionAction };
        }),
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  function toggle(section: string, action: PermissionAction) {
    const key = `${section}:${action}`;
    setGrants((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
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
          <span className="text-sm font-medium">Role name</span>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="dhcp-nat-l1"
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium">Description</span>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="optional"
          />
        </label>
      </div>

      <h3 className="mt-6 text-sm font-medium">Permissions matrix</h3>
      <p className="text-xs text-muted-foreground">
        Tick the actions this role can perform per section. Apply per-site or per-device scope when assigning the role to a user.
      </p>

      <Matrix label="Application" sections={grouped.app} grants={grants} onToggle={toggle} />
      <Matrix label="Devices" sections={grouped.driver} grants={grants} onToggle={toggle} />

      <div className="mt-6 flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {grants.size} permission{grants.size === 1 ? "" : "s"} selected
        </span>
        <button
          type="submit"
          disabled={m.isPending || grants.size === 0}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create role"}
        </button>
      </div>
    </form>
  );
}

function Matrix({
  label,
  sections,
  grants,
  onToggle,
}: {
  label: string;
  sections: SectionInfo[];
  grants: Set<string>;
  onToggle: (section: string, action: PermissionAction) => void;
}) {
  return (
    <div className="mt-4 overflow-hidden rounded-md border border-border">
      <div className="border-b border-border bg-muted/50 px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <table className="w-full text-sm">
        <thead className="border-b border-border bg-muted/20">
          <tr className="text-left">
            <th className="px-3 py-1.5 font-medium">Section</th>
            <th className="px-3 py-1.5 font-medium text-center">read</th>
            <th className="px-3 py-1.5 font-medium text-center">write</th>
            <th className="px-3 py-1.5 font-medium text-center">execute</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sections.map((s) => (
            <tr key={s.section}>
              <td className="px-3 py-1.5 font-mono text-xs">{s.section}</td>
              {(["read", "write", "execute"] as const).map((act) => {
                const supported = s.actions.includes(act);
                const key = `${s.section}:${act}`;
                return (
                  <td key={act} className="px-3 py-1.5 text-center">
                    {supported ? (
                      <input
                        type="checkbox"
                        checked={grants.has(key)}
                        onChange={() => onToggle(s.section, act)}
                        className="size-4 rounded"
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
