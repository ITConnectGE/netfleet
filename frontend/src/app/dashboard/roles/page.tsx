"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";

import {
  createRole,
  deleteRole,
  listRoles,
  listSections,
  updateRole,
  type Permission,
  type PermissionAction,
  type Role,
  type SectionInfo,
} from "@/lib/roles";

const ACTION_STYLES: Record<PermissionAction, string> = {
  read: "bg-sky-100 text-sky-900 dark:bg-sky-950/60 dark:text-sky-200",
  write: "bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-200",
  execute: "bg-rose-100 text-rose-900 dark:bg-rose-950/60 dark:text-rose-200",
};

/**
 * What each section governs, in plain English. Surfaced as the info-
 * tooltip body on every matrix row so a fresh admin doesn't have to
 * cross-reference docs to figure out e.g. "what does dhcp.lease
 * actually let me do". Kept here rather than on the backend because
 * the wording lives with the UI — translating it is a frontend job.
 */
const SECTION_DESCRIPTIONS: Record<string, string> = {
  // ---- Application ----
  tenants: "Customer organisations. Read = see the tenants list; write = create / rename / delete.",
  sites: "Physical locations under a tenant. Read = view sites + their devices on the map; write = create / move / delete sites.",
  devices: "Managed network devices (MikroTik routers, etc.). Read = view inventory + status; write = add / edit / delete a device row; execute = test connection, reboot.",
  users: "NetFleet portal accounts. Read = browse users + assignments; write = invite / disable / change password / assign roles.",
  roles: "This page. Read = view roles + their permissions; write = create / edit / delete roles.",
  audit: "Audit log of every state-changing action. Read-only.",
  events: "Per-device event stream (link flap, firewall drop, etc.). Read = browse; write = acknowledge / clear.",
  settings: "Org-wide settings — SMTP, SMS, OIDC, MFA toggles, backups. Read = view; write = save.",

  // ---- Driver ----
  "system.info": "Device identity (model, serial, uptime, clock, license). Read-only.",
  "system.reboot": "Soft-reboot the device. Execute only — there is no read or write here.",
  "system.backup": "RouterOS backup files. Read = list + download existing backups; execute = trigger a fresh backup.",
  "system.user": "On-device RouterOS users (`/user`). Read = list; write = add / edit / disable.",
  "interface.list": "Physical and virtual interfaces + interface lists. Read = view; write = enable / disable / reset counters / create VLANs.",
  "ip.address": "`/ip/address` table. Read = view assignments; write = add / remove.",
  "ip.route": "`/ip/route` table. Read = view; write = add / edit / delete static routes.",
  "ip.service": "RouterOS services (api, ssh, www). Read = view state + port; write = enable / disable / change port.",
  "ip.neighbor": "CDP / LLDP / MNDP neighbour discovery scope. Read = view; write = change discover-interface-list and protocol set.",
  "dhcp.server": "`/ip/dhcp-server` pools, networks, servers. Read = inspect config + leases; write = create / edit / delete.",
  "dhcp.lease": "DHCP leases (dynamic + static). Read = view; write = make static / delete / block.",
  "firewall.filter": "`/ip/firewall/filter` rules. Read = view; write = add / edit / move / enable / disable / reset counters.",
  "firewall.nat": "`/ip/firewall/nat` rules (src-nat, dst-nat, masquerade). Read = view; write = add / edit / move / enable / disable / reset counters.",
  "firewall.mangle": "`/ip/firewall/mangle` rules (mark-routing, mark-packet, change-MSS). Read = view; write = manage.",
  "queue.simple": "`/queue/simple` rate-limit policies. Read = view; write = add / edit / delete.",
  "queue.tree": "`/queue/tree` HTB hierarchy. Read = view; write = manage.",
  "ppp.secret": "`/ppp/secret` accounts (PPTP / L2TP / OpenVPN). Read = view; write = add / edit / disable. Secret reveal is gated separately.",
  "vpn.l2tp": "L2TP server + tunnels. Read = view; write = configure.",
  "vpn.pptp": "PPTP server + tunnels. Read = view; write = configure.",
  "vpn.ipsec": "IPsec policies + peers. Read = view; write = configure.",
  "vpn.sstp": "SSTP server. Read = view; write = configure.",
  "vpn.ovpn": "OpenVPN server. Read = view; write = configure.",
  "vpn.wireguard.interface": "WireGuard interfaces (listen port, keys). Read = view; write = add / edit / delete.",
  "vpn.wireguard.peer": "WireGuard peers (preshared keys, allowed-ips). Read = view; write = add / edit / delete.",
  "tool.ping": "Run `/ping` from the device. Execute only.",
  "tool.traceroute": "Run `/tool/traceroute`. Execute only.",
  "system.firmware": "Firmware checks + upgrades. Read = view current + available; execute = trigger an upgrade with reboot.",
  "secret.reveal":
    "Reveal stored plaintext secrets (device password, PPP secret, etc.). Audit-trailed; grant sparingly — this is the single most sensitive permission.",
};

function PermissionMatrix({ permissions }: { permissions: Permission[] }) {
  if (permissions.length === 0) {
    return (
      <p className="mt-3 text-xs italic text-muted-foreground">No permissions granted.</p>
    );
  }
  const bySection = new Map<string, PermissionAction[]>();
  for (const p of permissions) {
    const arr = bySection.get(p.section) ?? [];
    arr.push(p.action);
    bySection.set(p.section, arr);
  }
  const ordered = Array.from(bySection.entries()).sort(([a], [b]) => a.localeCompare(b));
  return (
    <div className="mt-3 space-y-1.5">
      {ordered.map(([section, actions]) => (
        <div key={section} className="flex items-baseline gap-2 text-xs">
          <span className="min-w-[7rem] font-mono text-muted-foreground">{section}</span>
          <div className="flex flex-wrap gap-1">
            {(["read", "write", "execute"] as const)
              .filter((a) => actions.includes(a))
              .map((a) => (
                <span
                  key={a}
                  className={`rounded-md px-1.5 py-0.5 font-mono text-[10px] ${ACTION_STYLES[a]}`}
                >
                  {a}
                </span>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

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
  const [editingId, setEditingId] = useState<string | null>(null);

  const del = useMutation({
    mutationFn: (id: string) => deleteRole(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["roles"] }),
  });

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <Link
            href="/dashboard/settings"
            className="text-xs text-muted-foreground hover:underline"
          >
            ← Settings
          </Link>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Access control</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Roles and the permission matrix. Assign them to users (with
            optional site- or device-level scope) from the Users page.
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
          onDone={() => {
            qc.invalidateQueries({ queryKey: ["roles"] });
            setShowForm(false);
          }}
          onCancel={() => setShowForm(false)}
        />
      )}

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {roles?.map((r) =>
          editingId === r.id && sections ? (
            <div key={r.id} className="md:col-span-2">
              <RoleForm
                sections={sections}
                existing={r}
                onDone={() => {
                  qc.invalidateQueries({ queryKey: ["roles"] });
                  setEditingId(null);
                }}
                onCancel={() => setEditingId(null)}
              />
            </div>
          ) : (
            <div key={r.id} className="rounded-lg border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
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
                  <div className="flex shrink-0 items-center gap-3 text-xs">
                    <button
                      onClick={() => setEditingId(r.id)}
                      className="text-muted-foreground hover:text-foreground hover:underline"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Delete role "${r.name}"?`)) del.mutate(r.id);
                      }}
                      className="text-destructive hover:underline"
                    >
                      Delete
                    </button>
                  </div>
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
              <PermissionMatrix permissions={r.permissions} />
            </div>
          ),
        )}
      </div>
    </div>
  );
}

function RoleForm({
  sections,
  existing,
  onDone,
  onCancel,
}: {
  sections: SectionInfo[];
  existing?: Role;
  onDone: () => void;
  onCancel: () => void;
}) {
  const isEdit = Boolean(existing);
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [grants, setGrants] = useState<Set<string>>(
    () => new Set(existing?.permissions.map((p) => `${p.section}:${p.action}`) ?? []),
  );
  const [error, setError] = useState<string | null>(null);

  const grouped = useMemo(() => {
    return {
      app: sections.filter((s) => s.kind === "app"),
      driver: sections.filter((s) => s.kind === "driver"),
    };
  }, [sections]);

  const m = useMutation({
    mutationFn: () => {
      const permissions = Array.from(grants).map((g) => {
        const [section, action] = g.split(":");
        return { section, action: action as PermissionAction };
      });
      if (existing) {
        return updateRole(existing.id, {
          name,
          description: description || null,
          permissions,
        });
      }
      return createRole({
        name,
        description: description || null,
        permissions,
      });
    },
    onSuccess: () => onDone(),
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

  function bulkSet(keys: string[], on: boolean) {
    setGrants((prev) => {
      const next = new Set(prev);
      for (const k of keys) {
        if (on) next.add(k);
        else next.delete(k);
      }
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
      <div className="flex items-start justify-between">
        <h3 className="text-sm font-semibold">
          {isEdit ? `Editing "${existing!.name}"` : "New role"}
        </h3>
        <button
          type="button"
          onClick={onCancel}
          className="text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          Cancel
        </button>
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="mt-4 grid gap-4 md:grid-cols-2">
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
            value={description ?? ""}
            onChange={(e) => setDescription(e.target.value)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <p className="text-[11px] italic text-muted-foreground">
            Optional · explain when this role is appropriate to assign
          </p>
        </label>
      </div>

      <h3 className="mt-6 text-sm font-medium">Permissions matrix</h3>
      <p className="text-xs text-muted-foreground">
        Tick the actions this role can perform per section. Apply per-site or per-device scope when assigning the role to a user.
      </p>

      <Matrix
        label="Application"
        sections={grouped.app}
        grants={grants}
        onToggle={toggle}
        onBulk={bulkSet}
      />
      <Matrix
        label="Devices"
        sections={grouped.driver}
        grants={grants}
        onToggle={toggle}
        onBulk={bulkSet}
      />

      <div className="mt-6 flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {grants.size} permission{grants.size === 1 ? "" : "s"} selected
        </span>
        <button
          type="submit"
          disabled={m.isPending || grants.size === 0}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? (isEdit ? "Saving…" : "Creating…") : isEdit ? "Save changes" : "Create role"}
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
  onBulk,
}: {
  label: string;
  sections: SectionInfo[];
  grants: Set<string>;
  onToggle: (section: string, action: PermissionAction) => void;
  onBulk: (keys: string[], on: boolean) => void;
}) {
  // Every (section, action) pair currently supported in this matrix —
  // the source of truth for the "Select all" toggle and for the
  // per-column header checkboxes.
  const allKeys = useMemo(
    () => sections.flatMap((s) => s.actions.map((a) => `${s.section}:${a}`)),
    [sections],
  );
  const granted = allKeys.filter((k) => grants.has(k)).length;
  const allOn = granted === allKeys.length && allKeys.length > 0;
  const someOn = granted > 0 && !allOn;

  function keysForAction(act: PermissionAction): string[] {
    return sections
      .filter((s) => s.actions.includes(act))
      .map((s) => `${s.section}:${act}`);
  }
  function columnState(act: PermissionAction): "all" | "some" | "none" {
    const ks = keysForAction(act);
    const on = ks.filter((k) => grants.has(k)).length;
    if (on === 0) return "none";
    if (on === ks.length) return "all";
    return "some";
  }

  return (
    <div className="mt-4 overflow-hidden rounded-md border border-border">
      <div className="flex items-center justify-between border-b border-border bg-muted/50 px-3 py-1.5">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground">
          <input
            type="checkbox"
            checked={allOn}
            ref={(el) => {
              if (el) el.indeterminate = someOn;
            }}
            onChange={() => onBulk(allKeys, !allOn)}
            className="size-3.5 rounded"
          />
          Select all in this section
        </label>
      </div>
      <table className="w-full text-sm">
        <thead className="border-b border-border bg-muted/20">
          <tr className="text-left">
            <th className="px-3 py-1.5 font-medium">Section</th>
            {(["read", "write", "execute"] as const).map((act) => {
              const state = columnState(act);
              return (
                <th key={act} className="px-3 py-1.5 text-center font-medium">
                  <label className="inline-flex cursor-pointer items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={state === "all"}
                      ref={(el) => {
                        if (el) el.indeterminate = state === "some";
                      }}
                      onChange={() =>
                        onBulk(keysForAction(act), state !== "all")
                      }
                      title={`Toggle every ${act} permission in ${label.toLowerCase()}`}
                      className="size-3.5 rounded"
                    />
                    {act}
                  </label>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sections.map((s) => (
            <tr key={s.section} className="hover:bg-accent/20">
              <td className="px-3 py-1.5">
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-xs">{s.section}</span>
                  <SectionInfoButton section={s.section} />
                </div>
              </td>
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

function SectionInfoButton({ section }: { section: string }) {
  const [open, setOpen] = useState(false);
  const description =
    SECTION_DESCRIPTIONS[section] ??
    "No description registered for this section yet.";
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={`What does ${section} grant?`}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault();
          setOpen((v) => !v);
        }}
        className="inline-flex size-4 items-center justify-center rounded-full border border-border bg-background text-[9px] font-semibold text-muted-foreground transition hover:border-primary/40 hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-5 top-0 z-30 w-72 rounded-md border border-border bg-popover px-3 py-2 text-[11px] leading-snug text-popover-foreground shadow-md"
        >
          {description}
        </span>
      )}
    </span>
  );
}
