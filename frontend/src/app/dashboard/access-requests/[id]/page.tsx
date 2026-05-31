"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useToast } from "@/components/toast";
import {
  approveAccessRequest,
  cancelAccessRequest,
  denyAccessRequest,
  getAccessRequest,
  type AccessRequestPublic,
} from "@/lib/access-requests";
import { fetchMe, type UserPublic } from "@/lib/auth";
import { listRoles, type Role } from "@/lib/roles";

export default function AccessRequestDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();

  const { data: req, isLoading } = useQuery<AccessRequestPublic>({
    queryKey: ["access-request", params.id],
    queryFn: () => getAccessRequest(params.id),
  });
  const { data: me } = useQuery<UserPublic | null>({
    queryKey: ["me"],
    queryFn: fetchMe,
  });
  const { data: roles } = useQuery<Role[]>({
    queryKey: ["roles"],
    queryFn: listRoles,
  });

  const cancel = useMutation({
    mutationFn: () => cancelAccessRequest(params.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["access-request", params.id] });
      qc.invalidateQueries({ queryKey: ["access-requests"] });
      toast.success("Request cancelled");
    },
    onError: (e: Error) => toast.error("Cancel failed", e.message),
  });

  if (isLoading || !req || !me) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const isAdmin = me.is_admin;
  const isRequester = me.id === req.requester_user_id;

  return (
    <div>
      <Link
        href="/dashboard/access-requests"
        className="text-xs text-muted-foreground hover:underline"
      >
        ← All access requests
      </Link>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">
        Access request
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Filed by {req.requester_display_name ?? req.requester_email} for{" "}
        <span className="font-mono">{req.scope_type}</span>
        {req.scope_label && (
          <>
            {" "}
            · <span>{req.scope_label}</span>
          </>
        )}
        .
      </p>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <section className="rounded-lg border border-border bg-card p-5">
          <h2 className="text-sm font-medium text-muted-foreground">Request</h2>
          <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
            <dt className="text-muted-foreground">Status</dt>
            <dd>
              <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium">
                {req.status}
              </span>
            </dd>
            <dt className="text-muted-foreground">Created</dt>
            <dd>{new Date(req.created_at).toLocaleString()}</dd>
            {req.decided_at && (
              <>
                <dt className="text-muted-foreground">Decided</dt>
                <dd>
                  {new Date(req.decided_at).toLocaleString()}
                  {req.decided_by_email && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      by {req.decided_by_email}
                    </span>
                  )}
                </dd>
              </>
            )}
            {req.granted_expires_at && (
              <>
                <dt className="text-muted-foreground">Expires</dt>
                <dd>{new Date(req.granted_expires_at).toLocaleString()}</dd>
              </>
            )}
          </dl>
          {req.reason && (
            <div className="mt-4">
              <div className="text-xs font-medium text-muted-foreground">
                Reason
              </div>
              <p className="mt-1 whitespace-pre-wrap rounded-md border border-border bg-background p-3 text-sm">
                {req.reason}
              </p>
            </div>
          )}
          {req.decision_note && (
            <div className="mt-4">
              <div className="text-xs font-medium text-muted-foreground">
                Admin note
              </div>
              <p className="mt-1 whitespace-pre-wrap rounded-md border border-border bg-background p-3 text-sm">
                {req.decision_note}
              </p>
            </div>
          )}
          {req.grants.length > 0 && (
            <div className="mt-4">
              <div className="text-xs font-medium text-muted-foreground">
                Granted
              </div>
              <ul className="mt-2 space-y-1 text-sm">
                {req.grants.map((g) => (
                  <li
                    key={g.assignment_id}
                    className="rounded-md border border-border bg-background px-2 py-1"
                  >
                    <span className="font-medium">{g.role_name}</span>
                    {g.expires_at && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        expires {new Date(g.expires_at).toLocaleString()}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {isRequester && req.status === "pending" && (
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => {
                  if (confirm("Cancel this access request?")) cancel.mutate();
                }}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
              >
                Cancel request
              </button>
            </div>
          )}
        </section>

        {isAdmin && req.status === "pending" && roles && (
          <DecideCard
            requestId={params.id}
            roles={roles}
            onDecided={() => {
              qc.invalidateQueries({ queryKey: ["access-request", params.id] });
              qc.invalidateQueries({ queryKey: ["access-requests"] });
              qc.invalidateQueries({ queryKey: ["notifications"] });
              router.push("/dashboard/access-requests");
            }}
          />
        )}
      </div>
    </div>
  );
}

function DecideCard({
  requestId,
  roles,
  onDecided,
}: {
  requestId: string;
  roles: Role[];
  onDecided: () => void;
}) {
  const toast = useToast();
  const [roleIds, setRoleIds] = useState<Set<string>>(new Set());
  const [expiresAt, setExpiresAt] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const approve = useMutation({
    mutationFn: () =>
      approveAccessRequest(requestId, {
        role_ids: Array.from(roleIds),
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        note: note.trim() || null,
      }),
    onSuccess: () => {
      toast.success("Approved");
      onDecided();
    },
    onError: (e: Error) => setError(e.message),
  });

  const deny = useMutation({
    mutationFn: () =>
      denyAccessRequest(requestId, { note: note.trim() || null }),
    onSuccess: () => {
      toast.success("Denied");
      onDecided();
    },
    onError: (e: Error) => setError(e.message),
  });

  function onApprove(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (roleIds.size === 0) {
      setError("Pick at least one role to grant.");
      return;
    }
    approve.mutate();
  }

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-sm font-medium text-muted-foreground">Decision</h2>
      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}
      <form onSubmit={onApprove} className="mt-3 space-y-4">
        <div>
          <div className="text-xs font-medium">Grant role(s)</div>
          <p className="text-[11px] text-muted-foreground">
            Each ticked role is bound to the requested scope. Inheritance
            applies — a tenant request becomes a tenant-scope assignment.
          </p>
          <ul className="mt-2 grid gap-1">
            {roles
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((r) => (
                <li key={r.id}>
                  <label className="flex items-start gap-2 rounded-md border border-border bg-background px-2 py-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={roleIds.has(r.id)}
                      onChange={(e) => {
                        const next = new Set(roleIds);
                        if (e.target.checked) next.add(r.id);
                        else next.delete(r.id);
                        setRoleIds(next);
                      }}
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
        </div>

        <label className="block space-y-1 text-sm font-medium">
          Expires at <span className="text-xs font-normal text-muted-foreground">(optional)</span>
          <input
            type="datetime-local"
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <p className="text-[11px] italic text-muted-foreground">
            Leave blank for a permanent grant.
          </p>
        </label>

        <label className="block space-y-1 text-sm font-medium">
          Note <span className="text-xs font-normal text-muted-foreground">(optional)</span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="Visible to the requester in their email + dashboard."
          />
        </label>

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={() => {
              setError(null);
              deny.mutate();
            }}
            disabled={deny.isPending || approve.isPending}
            className="rounded-md border border-destructive/40 bg-background px-3 py-1.5 text-sm font-medium text-destructive transition hover:bg-destructive/10 disabled:opacity-50"
          >
            {deny.isPending ? "Denying…" : "Deny"}
          </button>
          <button
            type="submit"
            disabled={approve.isPending || deny.isPending}
            className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {approve.isPending ? "Approving…" : "Approve"}
          </button>
        </div>
      </form>
    </section>
  );
}
