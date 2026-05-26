"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { formatBytes } from "@/lib/network";
import {
  createSimpleQueue,
  deleteSimpleQueue,
  listSimpleQueues,
  resetSimpleQueueCounters,
  type SimpleQueue,
} from "@/lib/queues";

export default function QueuesPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const qc = useQueryClient();

  const [showForm, setShowForm] = useState(false);
  const { data, isLoading, error } = useQuery<SimpleQueue[]>({
    queryKey: ["queues", deviceId],
    queryFn: () => listSimpleQueues(deviceId),
  });

  const del = useMutation({
    mutationFn: (id: string) => deleteSimpleQueue(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["queues", deviceId] }),
  });
  const reset = useMutation({
    mutationFn: (id: string) => resetSimpleQueueCounters(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["queues", deviceId] }),
  });

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Simple queues — bandwidth limits</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Per-IP / per-subnet bandwidth caps. Format is <code>upload/download</code> in bps with
            suffixes (e.g. <code>10M/10M</code>, <code>2500k/2500k</code>). Reset counters to
            zero a quota window.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New queue"}
        </button>
      </div>

      {showForm && (
        <QueueForm
          deviceId={deviceId}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["queues", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      <div className="mt-6 overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-3 py-2.5 font-medium">Name</th>
              <th className="px-3 py-2.5 font-medium">Target</th>
              <th className="px-3 py-2.5 font-medium">Max limit (up/dn)</th>
              <th className="px-3 py-2.5 font-medium">Burst limit</th>
              <th className="px-3 py-2.5 font-medium text-right">Used ↑</th>
              <th className="px-3 py-2.5 font-medium text-right">Used ↓</th>
              <th className="px-3 py-2.5 font-medium">Comment</th>
              <th className="px-3 py-2.5 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (!data || data.length === 0) && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">
                  No simple queues defined.
                </td>
              </tr>
            )}
            {data?.map((q) => (
              <tr
                key={q.id ?? q.name}
                className={`hover:bg-accent/30 ${q.disabled ? "opacity-50" : ""}`}
              >
                <td className="px-3 py-2 font-medium">{q.name}</td>
                <td className="px-3 py-2 font-mono text-xs">{q.target ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{q.max_limit ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{q.burst_limit ?? "—"}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatBytes(q.bytes_out)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatBytes(q.bytes_in)}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">{q.comment ?? "—"}</td>
                <td className="px-3 py-2 text-right">
                  {q.id && (
                    <>
                      <button
                        onClick={() => reset.mutate(q.id!)}
                        className="text-xs text-muted-foreground hover:underline"
                        title="Zero the byte counters"
                      >
                        Reset
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Delete queue "${q.name}"?`)) del.mutate(q.id!);
                        }}
                        className="ml-3 text-xs text-destructive hover:underline"
                      >
                        Delete
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QueueForm({
  deviceId,
  onCreated,
}: {
  deviceId: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [maxLimit, setMaxLimit] = useState("10M/10M");
  const [burstLimit, setBurstLimit] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createSimpleQueue(deviceId, {
        name,
        target: target || null,
        max_limit: maxLimit || null,
        burst_limit: burstLimit || null,
        comment: comment || null,
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        setError(null);
        m.mutate();
      }}
      className="mt-6 rounded-lg border border-border bg-card p-5"
    >
      {error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Name" htmlFor="q-n">
          <input
            id="q-n"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="user-nika"
          />
        </Field>
        <Field
          label="Target"
          htmlFor="q-t"
          hint="IPs / subnets / interfaces, comma-separated"
        >
          <input
            id="q-t"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.0.0.5,10.0.0.6"
          />
        </Field>
        <Field label="Max limit (upload/download)" htmlFor="q-ml">
          <input
            id="q-ml"
            value={maxLimit}
            onChange={(e) => setMaxLimit(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10M/10M"
          />
        </Field>
        <Field
          label="Burst limit"
          htmlFor="q-bl"
          hint="optional — short-term peak above max-limit"
        >
          <input
            id="q-bl"
            value={burstLimit}
            onChange={(e) => setBurstLimit(e.target.value)}
            className={`${input} font-mono`}
            placeholder="20M/20M"
          />
        </Field>
        <Field label="Comment" htmlFor="q-c">
          <input
            id="q-c"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={input}
          />
        </Field>
      </div>
      <div className="mt-5 flex justify-end">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Adding…" : "Add queue"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
        {hint && <span className="ml-2 text-xs font-normal text-muted-foreground">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
