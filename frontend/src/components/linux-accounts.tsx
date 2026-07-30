"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useToast } from "@/components/toast";
import {
  createDeviceGroup,
  createDeviceUser,
  deleteDeviceGroup,
  deleteDeviceUser,
  listDeviceGroups,
  listDeviceUsers,
  resetDeviceUserPassword,
  setDeviceUserDisabled,
  setDeviceUserGroups,
  type DeviceGroup,
  type DeviceUser,
} from "@/lib/device-ops";
import { cn } from "@/lib/utils";

/**
 * Unix accounts and groups.
 *
 * System accounts are hidden by default: a stock Ubuntu box has ~20 of
 * them and none are what an operator came here to manage, but hiding them
 * outright would be lying about what is on the host.
 */
export function LinuxAccounts({ deviceId }: { deviceId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [showSystem, setShowSystem] = useState(false);
  const [creating, setCreating] = useState(false);

  const { data: users, isLoading, error } = useQuery<DeviceUser[]>({
    queryKey: ["device-users", deviceId],
    queryFn: () => listDeviceUsers(deviceId),
  });
  const { data: groups } = useQuery<DeviceGroup[]>({
    queryKey: ["device-groups", deviceId],
    queryFn: () => listDeviceGroups(deviceId),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["device-users", deviceId] });
    qc.invalidateQueries({ queryKey: ["device-groups", deviceId] });
  };

  const toggleLock = useMutation({
    mutationFn: (v: { username: string; disabled: boolean }) =>
      setDeviceUserDisabled(deviceId, v.username, v.disabled),
    onSuccess: invalidate,
    onError: (e: Error) => toast.error("Could not change the account", e.message),
  });

  const remove = useMutation({
    mutationFn: (v: { username: string; removeHome: boolean }) =>
      deleteDeviceUser(deviceId, v.username, v.removeHome),
    onSuccess: (_r, v) => {
      invalidate();
      toast.success("Account deleted", v.username);
    },
    onError: (e: Error) => toast.error("Could not delete the account", e.message),
  });

  const visible = (users ?? []).filter((u) => showSystem || !u.is_system);

  return (
    <div className="space-y-6">
      <section>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Accounts</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Unix accounts on this host. NetFleet refuses to lock, delete or
              re-password <span className="font-mono">root</span> and the
              account it manages the host with — losing either means fixing the
              server from a console.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={showSystem}
                onChange={(e) => setShowSystem(e.target.checked)}
                className="size-3.5 rounded"
              />
              Show system accounts
            </label>
            <button
              type="button"
              onClick={() => setCreating((v) => !v)}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              {creating ? "Cancel" : "New account"}
            </button>
          </div>
        </div>

        {creating && (
          <CreateUserForm
            deviceId={deviceId}
            groups={groups ?? []}
            onDone={() => {
              setCreating(false);
              invalidate();
            }}
          />
        )}

        {isLoading && <p className="mt-3 text-sm text-muted-foreground">Reading…</p>}
        {error && (
          <p className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {(error as Error).message}
          </p>
        )}

        {users && (
          <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/60 text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Account</th>
                  <th className="px-3 py-2 font-medium">UID</th>
                  <th className="px-3 py-2 font-medium">Groups</th>
                  <th className="px-3 py-2 font-medium">Shell</th>
                  <th className="px-3 py-2 font-medium">Last login</th>
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {visible.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                      No regular accounts. Tick “Show system accounts” to see
                      the rest.
                    </td>
                  </tr>
                ) : (
                  visible.map((u) => (
                    <tr key={u.name} className="hover:bg-accent/30">
                      <td className="px-3 py-2 align-top">
                        <span className="font-mono font-medium">{u.name}</span>
                        {u.disabled && (
                          <span className="ml-2 rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-medium text-zinc-700">
                            locked
                          </span>
                        )}
                        {u.is_protected && (
                          <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900">
                            protected
                          </span>
                        )}
                        {u.comment && (
                          <span className="mt-0.5 block text-[11px] text-muted-foreground">
                            {u.comment}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 align-top font-mono text-xs">
                        {u.uid ?? "—"}
                      </td>
                      <td className="px-3 py-2 align-top text-xs">
                        <GroupEditor
                          deviceId={deviceId}
                          user={u}
                          allGroups={groups ?? []}
                          onDone={invalidate}
                        />
                      </td>
                      <td className="px-3 py-2 align-top font-mono text-[11px] text-muted-foreground">
                        {u.shell ?? "—"}
                      </td>
                      <td className="px-3 py-2 align-top text-[11px] text-muted-foreground">
                        {u.last_logged_in ?? "never"}
                      </td>
                      <td className="px-3 py-2 align-top text-right">
                        <div className="flex justify-end gap-1.5">
                          <PasswordButton
                            deviceId={deviceId}
                            user={u}
                            onDone={invalidate}
                          />
                          <button
                            type="button"
                            disabled={u.is_protected || toggleLock.isPending}
                            onClick={() =>
                              toggleLock.mutate({
                                username: u.name,
                                disabled: !u.disabled,
                              })
                            }
                            title={
                              u.is_protected
                                ? "NetFleet will not lock this account"
                                : undefined
                            }
                            className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {u.disabled ? "Unlock" : "Lock"}
                          </button>
                          <button
                            type="button"
                            disabled={u.is_protected || remove.isPending}
                            onClick={() => {
                              if (
                                !confirm(
                                  `Delete account "${u.name}"?\n\nOK also removes its home directory (${u.home ?? "unknown"}). Cancel to stop.`,
                                )
                              )
                                return;
                              remove.mutate({ username: u.name, removeHome: true });
                            }}
                            className="rounded-md border border-destructive/40 bg-background px-2 py-1 text-xs text-destructive hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <GroupsSection deviceId={deviceId} groups={groups ?? []} onDone={invalidate} />
    </div>
  );
}

function CreateUserForm({
  deviceId,
  groups,
  onDone,
}: {
  deviceId: string;
  groups: DeviceGroup[];
  onDone: () => void;
}) {
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [shell, setShell] = useState("/bin/bash");

  const m = useMutation({
    mutationFn: () =>
      createDeviceUser(deviceId, {
        username,
        password: password || null,
        groups: selected,
        shell,
        create_home: true,
      }),
    onSuccess: () => {
      toast.success(
        "Account created",
        password
          ? `${username} can log in with the password you set.`
          : `${username} was created without a password — key-only until you set one.`,
      );
      onDone();
    },
    onError: (e: Error) => toast.error("Could not create the account", e.message),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
      className="mt-3 rounded-lg border border-border bg-muted/20 p-4"
    >
      <div className="grid gap-3 md:grid-cols-4">
        <label className="block space-y-1 text-xs font-medium">
          Username
          <input
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="deploy"
            className={inputCls}
          />
          <span className="block font-normal text-muted-foreground">
            Lowercase, digits, - and _
          </span>
        </label>
        <label className="block space-y-1 text-xs font-medium">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            className={inputCls}
          />
          <span className="block font-normal text-muted-foreground">
            Leave empty for a key-only account
          </span>
        </label>
        <label className="block space-y-1 text-xs font-medium">
          Login shell
          <input
            value={shell}
            onChange={(e) => setShell(e.target.value)}
            className={`${inputCls} font-mono`}
          />
        </label>
        <div className="space-y-1 text-xs font-medium">
          Groups
          <div className="max-h-24 overflow-y-auto rounded-md border border-input bg-background p-2">
            {groups
              .filter((g) => !g.is_system || ["sudo", "docker", "adm"].includes(g.name))
              .map((g) => (
                <label key={g.name} className="flex items-center gap-1.5 font-normal">
                  <input
                    type="checkbox"
                    checked={selected.includes(g.name)}
                    onChange={(e) =>
                      setSelected((prev) =>
                        e.target.checked
                          ? [...prev, g.name]
                          : prev.filter((x) => x !== g.name),
                      )
                    }
                    className="size-3.5 rounded"
                  />
                  <span className="font-mono">{g.name}</span>
                </label>
              ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending || !username}
          className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create account"}
        </button>
      </div>
    </form>
  );
}

function GroupEditor({
  deviceId,
  user,
  allGroups,
  onDone,
}: {
  deviceId: string;
  user: DeviceUser;
  allGroups: DeviceGroup[];
  onDone: () => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(user.groups ?? []);

  const m = useMutation({
    mutationFn: () =>
      // The primary group is managed by the account itself, not by the
      // supplementary list usermod --groups replaces.
      setDeviceUserGroups(
        deviceId,
        user.name,
        selected.filter((g) => g !== user.group),
      ),
    onSuccess: () => {
      setOpen(false);
      onDone();
    },
    onError: (e: Error) => toast.error("Could not set groups", e.message),
  });

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setSelected(user.groups ?? []);
          setOpen(true);
        }}
        className="text-left hover:underline"
      >
        {user.groups?.length ? (
          <span className="font-mono">{user.groups.join(", ")}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </button>
    );
  }

  return (
    <div className="min-w-48 rounded-md border border-border bg-popover p-2 shadow-sm">
      <div className="max-h-40 overflow-y-auto">
        {allGroups.map((g) => (
          <label key={g.name} className="flex items-center gap-1.5">
            <input
              type="checkbox"
              disabled={g.name === user.group}
              checked={selected.includes(g.name)}
              onChange={(e) =>
                setSelected((prev) =>
                  e.target.checked
                    ? [...prev, g.name]
                    : prev.filter((x) => x !== g.name),
                )
              }
              className="size-3.5 rounded"
            />
            <span className={cn("font-mono", g.is_system && "text-muted-foreground")}>
              {g.name}
            </span>
            {g.name === user.group && (
              <span className="text-[10px] text-muted-foreground">primary</span>
            )}
          </label>
        ))}
      </div>
      <div className="mt-2 flex justify-end gap-1.5">
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-md border border-input px-2 py-0.5 text-[11px]"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => m.mutate()}
          disabled={m.isPending}
          className="rounded-md bg-primary px-2 py-0.5 text-[11px] text-primary-foreground disabled:opacity-50"
        >
          Save
        </button>
      </div>
    </div>
  );
}

function PasswordButton({
  deviceId,
  user,
  onDone,
}: {
  deviceId: string;
  user: DeviceUser;
  onDone: () => void;
}) {
  const toast = useToast();
  const m = useMutation({
    mutationFn: (pw: string) => resetDeviceUserPassword(deviceId, user.name, pw),
    onSuccess: () => {
      toast.success("Password set", user.name);
      onDone();
    },
    onError: (e: Error) => toast.error("Could not set the password", e.message),
  });

  return (
    <button
      type="button"
      disabled={user.is_protected || m.isPending}
      onClick={() => {
        const pw = prompt(`New password for "${user.name}":`);
        if (pw) m.mutate(pw);
      }}
      title={
        user.is_protected ? "NetFleet will not change this account's password" : undefined
      }
      className="rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
    >
      Password
    </button>
  );
}

function GroupsSection({
  deviceId,
  groups,
  onDone,
}: {
  deviceId: string;
  groups: DeviceGroup[];
  onDone: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [showSystem, setShowSystem] = useState(false);

  const create = useMutation({
    mutationFn: () => createDeviceGroup(deviceId, name),
    onSuccess: () => {
      setName("");
      onDone();
    },
    onError: (e: Error) => toast.error("Could not create the group", e.message),
  });
  const remove = useMutation({
    mutationFn: (g: string) => deleteDeviceGroup(deviceId, g),
    onSuccess: onDone,
    onError: (e: Error) => toast.error("Could not delete the group", e.message),
  });

  const visible = groups.filter((g) => showSystem || !g.is_system);

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-semibold">Groups</h2>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={showSystem}
            onChange={(e) => setShowSystem(e.target.checked)}
            className="size-3.5 rounded"
          />
          Show system groups
        </label>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
        className="mt-2 flex gap-2"
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New group name"
          className="w-56 rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="submit"
          disabled={!name || create.isPending}
          className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          Add group
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {visible.map((g) => (
          <span
            key={g.name}
            className="inline-flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1 text-xs"
          >
            <span className="font-mono">{g.name}</span>
            <span className="text-muted-foreground">{g.gid}</span>
            {g.members.length > 0 && (
              <span className="text-muted-foreground" title={g.members.join(", ")}>
                · {g.members.length}
              </span>
            )}
            {!g.is_system && (
              <button
                type="button"
                onClick={() => {
                  if (confirm(`Delete group "${g.name}"?`)) remove.mutate(g.name);
                }}
                className="text-destructive hover:underline"
                aria-label={`Delete group ${g.name}`}
              >
                ×
              </button>
            )}
          </span>
        ))}
      </div>
    </section>
  );
}

const inputCls =
  "block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm font-normal shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
