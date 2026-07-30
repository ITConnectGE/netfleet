"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

import { LinuxAccounts } from "@/components/linux-accounts";
import { getDevice, type Device } from "@/lib/devices";

import {
  listDeviceUsers,
  resetDeviceUserPassword,
  setDeviceUserDisabled,
  type DeviceUser,
} from "@/lib/device-ops";

export default function DeviceSystemUsersPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const qc = useQueryClient();
  const [resettingFor, setResettingFor] = useState<string | null>(null);

  const { data: device } = useQuery<Device>({
    queryKey: ["device", deviceId],
    queryFn: () => getDevice(deviceId),
    enabled: Boolean(deviceId),
  });

  const isServer = device?.device_class === "server";

  const { data: users, isLoading, error } = useQuery<DeviceUser[]>({
    queryKey: ["device-users", deviceId],
    queryFn: () => listDeviceUsers(deviceId),
    // The Linux view fetches this itself; skipping it here avoids two
    // requests for the same list on every render of a server.
    enabled: Boolean(deviceId) && !isServer,
  });

  const disableMut = useMutation({
    mutationFn: ({ username, disabled }: { username: string; disabled: boolean }) =>
      setDeviceUserDisabled(deviceId, username, disabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["device-users", deviceId] }),
  });

  // Unix accounts and RouterOS users share a tab but almost nothing else:
  // one has UIDs, supplementary groups, a login shell and a home
  // directory, the other has a permission-bundle "group" and neither of
  // the rest. Rendering both through one table would show empty columns to
  // each. Placed after every hook — an early return above them would make
  // the hook order depend on which device is loaded.
  if (isServer) {
    return <LinuxAccounts deviceId={deviceId} />;
  }

  return (
    <div>
      <h2 className="text-lg font-semibold">Device users</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Router-local accounts. Reset passwords or disable here. Every action is recorded in the audit log.
      </p>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Group</th>
              <th className="px-4 py-2.5 font-medium">Last login</th>
              <th className="px-4 py-2.5 font-medium">Comment</th>
              <th className="px-4 py-2.5 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {users?.map((u) => (
              <tr key={u.name} className="hover:bg-accent/30">
                <td className="px-4 py-3 font-mono">
                  {u.name}
                  {u.disabled && (
                    <span className="ml-2 rounded-md bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-800">
                      disabled
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-xs">{u.group ?? "—"}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {u.last_logged_in ?? "never"}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{u.comment ?? "—"}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => setResettingFor(u.name)}
                    className="text-xs text-primary hover:underline"
                  >
                    Reset password
                  </button>
                  <button
                    onClick={() => {
                      disableMut.mutate({ username: u.name, disabled: !u.disabled });
                    }}
                    className="ml-3 text-xs text-muted-foreground hover:underline"
                  >
                    {u.disabled ? "Enable" : "Disable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {resettingFor && (
        <PasswordResetModal
          deviceId={deviceId}
          username={resettingFor}
          onClose={() => setResettingFor(null)}
        />
      )}
    </div>
  );
}

function PasswordResetModal({
  deviceId,
  username,
  onClose,
}: {
  deviceId: string;
  username: string;
  onClose: () => void;
}) {
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const m = useMutation({
    mutationFn: () => resetDeviceUserPassword(deviceId, username, pw),
    onSuccess: () => setDone(true),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-lg">
        <h3 className="text-lg font-semibold">Reset password for {username}</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          The new password is written directly to the device. Audit logged.
        </p>

        {error && (
          <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}
        {done ? (
          <div className="mt-4">
            <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
              Password updated on the device.
            </div>
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Close
            </button>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              if (pw.length < 8) {
                setError("Password must be at least 8 characters.");
                return;
              }
              if (pw !== confirm) {
                setError("Passwords do not match.");
                return;
              }
              m.mutate();
            }}
            className="mt-4 space-y-3"
          >
            <input
              type="password"
              required
              minLength={8}
              placeholder="new password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              autoComplete="new-password"
            />
            <input
              type="password"
              required
              placeholder="confirm"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              autoComplete="new-password"
            />
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={m.isPending}
                className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                {m.isPending ? "Resetting…" : "Reset password"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
