"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import {
  getUpdateStatus,
  isInProgress,
  triggerUpdate,
  type UpdateState,
  type UpdateStatus,
} from "@/lib/updates";

export default function UpdatesPage() {
  const qc = useQueryClient();
  const { data, isLoading, error, dataUpdatedAt } = useQuery<UpdateStatus>({
    queryKey: ["update-status"],
    queryFn: getUpdateStatus,
    // Poll fast while a job is running, slow otherwise
    refetchInterval: (q) => (q.state.data && isInProgress(q.state.data.state) ? 2000 : 30_000),
  });

  const [confirming, setConfirming] = useState(false);
  const [confirmBackup, setConfirmBackup] = useState(true);

  const m = useMutation({
    mutationFn: () => triggerUpdate(data!.available!, confirmBackup),
    onSuccess: () => {
      setConfirming(false);
      qc.invalidateQueries({ queryKey: ["update-status"] });
    },
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error || !data) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {(error as Error)?.message ?? "updater not reachable"}
      </div>
    );
  }

  const hasUpdate = Boolean(data.available);
  const running = isInProgress(data.state);

  return (
    <div className="space-y-8">
      <div>
        <Link href="/dashboard/settings" className="text-xs text-muted-foreground hover:underline">
          ← Settings
        </Link>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">In-app updates</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Upgrade NetFleet to a newer release published on{" "}
          <a
            href={`https://github.com/${data.repo}/releases`}
            target="_blank"
            rel="noreferrer"
            className="text-primary hover:underline"
          >
            {data.repo}
          </a>
          . Channel: <span className="font-mono">{data.channel}</span>.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Current version">
          <p className="mt-1 font-mono text-2xl">{data.current}</p>
        </Card>
        <Card title="Available">
          {data.available ? (
            <p className="mt-1 font-mono text-2xl text-amber-700">{data.available}</p>
          ) : (
            <p className="mt-1 text-sm text-emerald-700">up to date</p>
          )}
        </Card>
        <Card title="Last checked">
          <p className="mt-1 text-sm text-muted-foreground">
            {data.last_checked_iso
              ? new Date(data.last_checked_iso).toLocaleString()
              : "—"}
          </p>
          {dataUpdatedAt > 0 && (
            <p className="text-xs text-muted-foreground">
              this page: {new Date(dataUpdatedAt).toLocaleTimeString()}
            </p>
          )}
        </Card>
      </div>

      {/* Action area */}
      <div className="rounded-lg border border-border bg-card p-6">
        {running ? (
          <ProgressView data={data} />
        ) : hasUpdate ? (
          <UpgradePrompt
            data={data}
            confirming={confirming}
            backup={confirmBackup}
            onBackup={setConfirmBackup}
            onAskConfirm={() => setConfirming(true)}
            onCancel={() => setConfirming(false)}
            onConfirm={() => m.mutate()}
            pending={m.isPending}
            error={m.error ? (m.error as Error).message : null}
          />
        ) : data.state === "success" ? (
          <UpToDate banner="✓ Update completed." log={data.log_tail} />
        ) : data.state === "failed" ? (
          <UpdateFailed err={data.last_error} log={data.log_tail} />
        ) : (
          <p className="text-sm text-muted-foreground">
            You&apos;re on the latest stable release.
          </p>
        )}
      </div>

      <PostUpdateNotes />
    </div>
  );
}

// ---------------- Sub-components ----------------

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{title}</p>
      {children}
    </div>
  );
}

function UpgradePrompt({
  data,
  confirming,
  backup,
  onBackup,
  onAskConfirm,
  onCancel,
  onConfirm,
  pending,
  error,
}: {
  data: UpdateStatus;
  confirming: boolean;
  backup: boolean;
  onBackup: (v: boolean) => void;
  onAskConfirm: () => void;
  onCancel: () => void;
  onConfirm: () => void;
  pending: boolean;
  error: string | null;
}) {
  if (!confirming) {
    return (
      <div className="flex items-start justify-between gap-6">
        <div>
          <h2 className="text-lg font-semibold">
            {data.available} is ready to install
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            The api, worker, and web containers will be recreated; postgres, redis, caddy,
            and the updater itself keep running. Active sessions will briefly disconnect
            (~30 seconds while the new api comes back).
          </p>
          {data.last_error && (
            <p className="mt-2 text-xs text-muted-foreground">
              Last error from a previous attempt: <span className="font-mono">{data.last_error}</span>
            </p>
          )}
        </div>
        <button
          onClick={onAskConfirm}
          className="shrink-0 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Update to {data.available}
        </button>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-lg font-semibold">Confirm upgrade</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Upgrading from <span className="font-mono">{data.current}</span> to{" "}
        <span className="font-mono">{data.available}</span>. This action is logged in the
        audit log.
      </p>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <label className="mt-4 flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={backup}
          onChange={(e) => onBackup(e.target.checked)}
          className="mt-0.5 size-4 rounded"
        />
        <span>
          Take a pre-update <code>pg_dump</code> of the application database first.
          Strongly recommended. The dump lands in <code>/opt/netfleet/data/backups/</code>.
        </span>
      </label>

      <div className="mt-5 flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="rounded-md border border-input bg-background px-4 py-2 text-sm hover:bg-accent"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={pending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {pending ? "Starting…" : `Start update to ${data.available}`}
        </button>
      </div>
    </div>
  );
}

const STEPS: { key: UpdateState; label: string }[] = [
  { key: "backing_up", label: "Backup" },
  { key: "pulling", label: "Pull images" },
  { key: "recreating", label: "Recreate services" },
  { key: "health_checking", label: "Health check" },
];

function ProgressView({ data }: { data: UpdateStatus }) {
  const currentIdx = STEPS.findIndex((s) => s.key === data.state);

  return (
    <div>
      <h2 className="text-lg font-semibold">
        Updating → <span className="font-mono">{data.target_version ?? "?"}</span>
      </h2>

      <ol className="mt-5 grid grid-cols-4 gap-2 text-xs">
        {STEPS.map((s, i) => {
          const state =
            i < currentIdx ? "done" : i === currentIdx ? "active" : "pending";
          return (
            <li
              key={s.key}
              className={`rounded-md border px-3 py-2 ${
                state === "done"
                  ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                  : state === "active"
                    ? "border-sky-300 bg-sky-50 text-sky-900"
                    : "border-border bg-muted/40 text-muted-foreground"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px]">{i + 1}.</span>
                <span className="font-medium">{s.label}</span>
              </div>
              <div className="mt-0.5 text-[10px] uppercase tracking-wider">
                {state === "active" ? "running" : state}
              </div>
            </li>
          );
        })}
      </ol>

      <LogTail lines={data.log_tail} />
    </div>
  );
}

function UpToDate({ banner, log }: { banner: string; log: string[] }) {
  return (
    <div>
      <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
        {banner}
      </div>
      <LogTail lines={log} />
    </div>
  );
}

function UpdateFailed({ err, log }: { err: string | null; log: string[] }) {
  return (
    <div>
      <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        <strong>Update failed.</strong>{" "}
        {err ?? "No detail. Check the log below."} Your previous version is still running —
        nothing was destroyed except possibly a half-pulled image.
      </div>
      <LogTail lines={log} />
    </div>
  );
}

function LogTail({ lines }: { lines: string[] }) {
  if (!lines || lines.length === 0) return null;
  return (
    <details className="mt-4 rounded-md border border-border bg-muted/30" open>
      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
        Log ({lines.length} lines)
      </summary>
      <pre className="max-h-72 overflow-auto px-3 py-2 font-mono text-[11px] leading-relaxed">
        {lines.join("\n")}
      </pre>
    </details>
  );
}

function PostUpdateNotes() {
  return (
    <div className="rounded-md border border-dashed border-border bg-muted/20 p-4 text-xs text-muted-foreground">
      <p className="font-medium text-foreground">After the update</p>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        <li>
          The browser session may briefly show 502 while the api restarts — refresh and you&apos;re back in.
        </li>
        <li>
          New Alembic migrations run on api startup. If you see a migration error in the
          log, the previous version stays online; you can roll back manually with{" "}
          <code>VERSION=v0.x docker compose up -d</code> on the host.
        </li>
        <li>
          The pre-update <code>pg_dump</code> lands in{" "}
          <code>/opt/netfleet/data/backups/pre-update-&lt;ver&gt;-&lt;ts&gt;.sql.gz</code>.
        </li>
      </ul>
    </div>
  );
}
