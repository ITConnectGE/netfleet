"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { listLogs, type LogEntry } from "@/lib/firewall";

const POLL_INTERVAL_MS = 5000;
const LIMITS = [200, 500, 1000, 2000] as const;
type Limit = (typeof LIMITS)[number];

export default function DeviceLogsPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;

  const [topics, setTopics] = useState<string>("");
  const [limit, setLimit] = useState<Limit>(500);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [clientFilter, setClientFilter] = useState<string>("");

  const { data, isFetching, error, dataUpdatedAt } = useQuery<LogEntry[]>({
    queryKey: ["device-logs", deviceId, topics, limit],
    queryFn: () => listLogs(deviceId, { topics: topics || undefined, limit }),
    refetchInterval: paused ? false : POLL_INTERVAL_MS,
    // Don't poll while the browser tab is in the background — the user
    // isn't watching and the device call is real bandwidth.
    refetchIntervalInBackground: false,
    // Keep previous rows on screen during refetch so the viewer doesn't
    // flicker / scroll-jump.
    placeholderData: (prev) => prev,
  });

  // Client-side substring filter — separate from `topics`, which drives the
  // device-side filter and triggers a refetch.
  const visible = useMemo(() => {
    if (!data) return [];
    if (!clientFilter.trim()) return data;
    const needle = clientFilter.toLowerCase();
    return data.filter(
      (r) =>
        r.message.toLowerCase().includes(needle) ||
        r.topics.toLowerCase().includes(needle) ||
        r.time.toLowerCase().includes(needle),
    );
  }, [data, clientFilter]);

  const scrollerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!autoScroll || !scrollerRef.current) return;
    scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [visible, autoScroll]);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Logs</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            RouterOS in-memory log buffer (<code>/log/print</code>). Polled every
            5 s. To retain more than the default ~1000 lines, configure{" "}
            <code>/system logging</code> with <code>action=disk</code> on the device.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 ${
              paused
                ? "bg-zinc-100 text-zinc-700"
                : isFetching
                  ? "bg-amber-100 text-amber-900"
                  : "bg-emerald-100 text-emerald-800"
            }`}
          >
            <span
              className={`size-1.5 rounded-full ${
                paused
                  ? "bg-zinc-400"
                  : isFetching
                    ? "animate-pulse bg-amber-500"
                    : "bg-emerald-500"
              }`}
            />
            {paused ? "paused" : isFetching ? "fetching" : "live"}
          </span>
          {dataUpdatedAt > 0 && (
            <span className="text-muted-foreground">
              · last refresh {new Date(dataUpdatedAt).toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-3 rounded-lg border border-border bg-card p-3 md:grid-cols-[1.5fr_1.5fr_1fr_auto_auto]">
        <Field
          label="Topics (device-side)"
          hint="comma-separated e.g. firewall,info or dhcp,!debug"
        >
          <input
            value={topics}
            onChange={(e) => setTopics(e.target.value)}
            placeholder="all topics"
            className={input}
          />
        </Field>
        <Field label="Search in results (client-side)">
          <input
            value={clientFilter}
            onChange={(e) => setClientFilter(e.target.value)}
            placeholder="substring (case-insensitive)"
            className={input}
          />
        </Field>
        <Field label="Buffer size">
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value) as Limit)}
            className={input}
          >
            {LIMITS.map((n) => (
              <option key={n} value={n}>
                last {n}
              </option>
            ))}
          </select>
        </Field>
        <label className="flex items-end gap-1.5 pb-2 text-xs">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          <span>Auto-scroll</span>
        </label>
        <div className="flex items-end pb-1">
          <button
            onClick={() => setPaused((p) => !p)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
              paused
                ? "bg-emerald-600 text-white hover:bg-emerald-700"
                : "bg-zinc-200 text-zinc-900 hover:bg-zinc-300"
            }`}
          >
            {paused ? "Resume" : "Pause"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      <div
        ref={scrollerRef}
        className="mt-4 h-[60vh] overflow-auto rounded-lg border border-border bg-zinc-950 p-3 font-mono text-[11px] text-zinc-100"
      >
        {visible.length === 0 ? (
          <div className="flex h-full items-center justify-center text-zinc-500">
            {data ? "No log lines match the current filters." : "Loading…"}
          </div>
        ) : (
          <div className="space-y-0.5">
            {visible.map((r, i) => (
              <LogLine key={i} entry={r} />
            ))}
          </div>
        )}
      </div>

      <p className="mt-2 text-[11px] text-muted-foreground">
        Showing {visible.length}
        {data && visible.length !== data.length ? ` of ${data.length}` : ""} entries.
        Polling pauses automatically while the browser tab is in the background.
      </p>
    </div>
  );
}

function LogLine({ entry }: { entry: LogEntry }) {
  const topics = entry.topics.split(",").map((t) => t.trim()).filter(Boolean);
  return (
    <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-2 leading-snug">
      <span className="shrink-0 text-zinc-500">{entry.time}</span>
      <div className="min-w-0">
        <span className="mr-1.5">
          {topics.map((t) => (
            <TopicPill key={t} topic={t} />
          ))}
        </span>
        <span className={messageClass(topics)}>{entry.message}</span>
      </div>
    </div>
  );
}

function TopicPill({ topic }: { topic: string }) {
  return (
    <span
      className={`mr-0.5 rounded px-1 py-0.5 text-[9px] font-medium ${topicColor(topic)}`}
    >
      {topic}
    </span>
  );
}

function topicColor(topic: string): string {
  if (["error", "critical"].includes(topic)) return "bg-red-900/60 text-red-100";
  if (topic === "warning") return "bg-amber-900/60 text-amber-100";
  if (topic === "firewall") return "bg-purple-900/60 text-purple-100";
  if (["dhcp", "dhcp4", "dhcp6"].includes(topic))
    return "bg-sky-900/60 text-sky-100";
  if (["wireless", "interface"].includes(topic))
    return "bg-emerald-900/60 text-emerald-100";
  if (topic === "info") return "bg-zinc-700 text-zinc-200";
  if (topic === "debug") return "bg-zinc-800 text-zinc-400";
  return "bg-zinc-700 text-zinc-200";
}

function messageClass(topics: string[]): string {
  if (topics.some((t) => ["error", "critical"].includes(t))) return "text-red-200";
  if (topics.some((t) => t === "warning")) return "text-amber-200";
  return "text-zinc-200";
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1 text-xs">
      <span className="font-medium text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="block text-[10px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

const input =
  "block w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
