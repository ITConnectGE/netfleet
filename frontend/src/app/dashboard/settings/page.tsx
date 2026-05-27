"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import {
  getSmtpSettings,
  testSmtp,
  updateSmtpSettings,
  type SmtpSettings,
  type SmtpSettingsUpdate,
  type SmtpTestResult,
} from "@/lib/settings";

export default function SettingsPage() {
  return (
    <div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Org-wide configuration. Saved to the database; takes effect immediately.
        </p>
      </div>

      <div className="mt-8 max-w-3xl space-y-8">
        <Link
          href="/dashboard/settings/updates"
          className="block rounded-lg border border-border bg-card p-5 transition hover:border-primary/40"
        >
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold">In-app updates</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Check for a newer NetFleet release and upgrade with one click. Pre-update
                Postgres backup included.
              </p>
            </div>
            <span className="text-sm text-primary">Open →</span>
          </div>
        </Link>

        <SmtpSection />
      </div>
    </div>
  );
}

function SmtpSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<SmtpSettings>({
    queryKey: ["smtp-settings"],
    queryFn: getSmtpSettings,
  });

  const [draft, setDraft] = useState<SmtpSettingsUpdate>({});
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [testTo, setTestTo] = useState("");
  const [testResult, setTestResult] = useState<SmtpTestResult | null>(null);

  // Hydrate draft once data arrives.
  useEffect(() => {
    if (data) {
      setDraft({
        smtp_enabled: data.smtp_enabled,
        smtp_host: data.smtp_host ?? "",
        smtp_port: data.smtp_port,
        smtp_username: data.smtp_username ?? "",
        smtp_from_email: data.smtp_from_email ?? "",
        smtp_from_name: data.smtp_from_name ?? "",
        smtp_use_tls: data.smtp_use_tls,
        smtp_use_starttls: data.smtp_use_starttls,
      });
      setPasswordTouched(false);
    }
  }, [data]);

  const save = useMutation({
    mutationFn: () => {
      const payload: SmtpSettingsUpdate = { ...draft };
      // Only send smtp_password if the user actually edited it (avoid overwriting with "").
      if (!passwordTouched) delete payload.smtp_password;
      // Empty strings become null on optional text fields.
      const stringFields: (keyof SmtpSettingsUpdate)[] = [
        "smtp_host",
        "smtp_username",
        "smtp_from_email",
        "smtp_from_name",
      ];
      for (const k of stringFields) {
        if (payload[k] === "") (payload as Record<string, unknown>)[k] = null;
      }
      return updateSmtpSettings(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["smtp-settings"] });
      setSavedAt(Date.now());
      setError(null);
      setPasswordTouched(false);
    },
    onError: (e: Error) => setError(e.message),
  });

  const test = useMutation({
    mutationFn: () => testSmtp(testTo),
    onSuccess: (r) => setTestResult(r),
    onError: (e: Error) => setTestResult({ ok: false, error: e.message }),
  });

  if (isLoading || !data) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        setError(null);
        save.mutate();
      }}
      className="rounded-lg border border-border bg-card p-6"
    >
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold">SMTP / Email</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Used for invites, password resets, and (future) alert notifications.
          </p>
        </div>
        <label className="flex shrink-0 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.smtp_enabled ?? false}
            onChange={(e) => setDraft((d) => ({ ...d, smtp_enabled: e.target.checked }))}
            className="size-4 rounded"
          />
          Enabled
        </label>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      {savedAt && !error && (
        <div className="mt-4 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          Saved.
        </div>
      )}

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <Field label="SMTP host">
          <input
            type="text"
            placeholder="smtp.example.com"
            value={draft.smtp_host ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, smtp_host: e.target.value }))}
            className={inputClass}
          />
        </Field>
        <Field label="Port">
          <input
            type="number"
            min={1}
            max={65535}
            value={draft.smtp_port ?? 587}
            onChange={(e) => setDraft((d) => ({ ...d, smtp_port: Number(e.target.value) }))}
            className={inputClass}
          />
        </Field>
        <Field label="Username">
          <input
            type="text"
            autoComplete="off"
            value={draft.smtp_username ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, smtp_username: e.target.value }))}
            className={inputClass}
          />
        </Field>
        <Field
          label="Password"
          hint={
            data.has_smtp_password && !passwordTouched
              ? "Leave blank to keep the existing password"
              : undefined
          }
        >
          <input
            type="password"
            autoComplete="new-password"
            placeholder={data.has_smtp_password ? "•••••••• (set)" : ""}
            value={draft.smtp_password ?? ""}
            onChange={(e) => {
              setDraft((d) => ({ ...d, smtp_password: e.target.value }));
              setPasswordTouched(true);
            }}
            className={inputClass}
          />
        </Field>
        <Field label="From email">
          <input
            type="email"
            placeholder="noreply@example.com"
            value={draft.smtp_from_email ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, smtp_from_email: e.target.value }))}
            className={inputClass}
          />
        </Field>
        <Field label="From name (optional)">
          <input
            type="text"
            placeholder="NetFleet"
            value={draft.smtp_from_name ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, smtp_from_name: e.target.value }))}
            className={inputClass}
          />
        </Field>
      </div>

      <fieldset className="mt-5 rounded-md border border-border p-4">
        <legend className="px-2 text-xs font-medium text-muted-foreground">TLS</legend>
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.smtp_use_starttls ?? true}
              onChange={(e) => setDraft((d) => ({ ...d, smtp_use_starttls: e.target.checked }))}
              className="size-4 rounded"
            />
            Use STARTTLS (port 587, modern default)
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.smtp_use_tls ?? true}
              onChange={(e) => setDraft((d) => ({ ...d, smtp_use_tls: e.target.checked }))}
              className="size-4 rounded"
            />
            Encrypt the connection (recommended)
          </label>
          <p className="text-xs text-muted-foreground">
            Implicit-TLS providers (port 465) want{" "}
            <span className="font-medium">Encrypt = on, STARTTLS = off</span>.
          </p>
        </div>
      </fieldset>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <button
          type="submit"
          disabled={save.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="email"
            placeholder="send test to…"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
            className="w-64 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="button"
            onClick={() => {
              setTestResult(null);
              test.mutate();
            }}
            disabled={test.isPending || !testTo}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
          >
            {test.isPending ? "Sending…" : "Send test"}
          </button>
        </div>
      </div>

      {testResult && (
        <div
          className={`mt-4 rounded-md border px-3 py-2 text-sm ${
            testResult.ok
              ? "border-emerald-300 bg-emerald-50 text-emerald-900"
              : "border-red-300 bg-red-50 text-red-900"
          }`}
        >
          {testResult.ok
            ? `Test email sent to ${testTo}. Check the inbox.`
            : `Failed: ${testResult.error ?? "unknown error"}`}
        </div>
      )}
    </form>
  );
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
    <label className="block space-y-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
      {hint && <span className="block text-[10px] text-muted-foreground">{hint}</span>}
    </label>
  );
}

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring";
