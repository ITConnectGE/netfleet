"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import {
  getOrgInfo,
  getSmsPresets,
  getSmsSettings,
  getSmtpSettings,
  testSms,
  testSmtp,
  updateOrgInfo,
  updateSmsSettings,
  updateSmtpSettings,
  type OrgInfo,
  type SmsProviderPreset,
  type SmsSettings,
  type SmsSettingsUpdate,
  type SmsTestResult,
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

        <OrgInfoSection />
        <SmtpSection />
        <SmsSection />
      </div>
    </div>
  );
}

function OrgInfoSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<OrgInfo>({
    queryKey: ["org-info"],
    queryFn: getOrgInfo,
  });
  const [value, setValue] = useState("");
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data) setValue(data.netfleet_external_ips ?? "");
  }, [data]);

  const save = useMutation({
    mutationFn: () => updateOrgInfo({ netfleet_external_ips: value || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-info"] });
      setSavedAt(Date.now());
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
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
      <h2 className="text-lg font-semibold">NetFleet external IP(s)</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        The egress IP(s) managed devices see when NetFleet connects to them.
        Used to whitelist NetFleet in the device-onboarding script. Comma-
        separated IPs or CIDRs (e.g. <code>203.0.113.10,198.51.100.0/29</code>).
      </p>

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

      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="203.0.113.10,198.51.100.0/29"
        className={`${inputClass} mt-4 font-mono text-sm`}
      />
      <div className="mt-4 flex justify-end">
        <button
          type="submit"
          disabled={save.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function SmsSection() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<SmsSettings>({
    queryKey: ["sms-settings"],
    queryFn: getSmsSettings,
  });
  const { data: presets } = useQuery<SmsProviderPreset[]>({
    queryKey: ["sms-presets"],
    queryFn: getSmsPresets,
  });

  const [draft, setDraft] = useState<SmsSettingsUpdate>({});
  const [keyTouched, setKeyTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [testTo, setTestTo] = useState("");
  const [testText, setTestText] = useState("NetFleet SMS test");
  const [testResult, setTestResult] = useState<SmsTestResult | null>(null);

  useEffect(() => {
    if (data) {
      setDraft({
        sms_enabled: data.sms_enabled,
        sms_provider: data.sms_provider,
        sms_api_url: data.sms_api_url ?? "",
        sms_http_method: data.sms_http_method,
        sms_body_format: data.sms_body_format,
        sms_body_template: data.sms_body_template ?? "",
        sms_auth_header_name: data.sms_auth_header_name ?? "",
        sms_auth_header_value_template: data.sms_auth_header_value_template ?? "",
        sms_sender: data.sms_sender ?? "",
        sms_success_status_min: data.sms_success_status_min,
        sms_success_status_max: data.sms_success_status_max,
        sms_success_body_contains: data.sms_success_body_contains ?? "",
        sms_timeout_seconds: data.sms_timeout_seconds,
      });
      setKeyTouched(false);
    }
  }, [data]);

  const applyPreset = (key: string) => {
    const p = presets?.find((x) => x.key === key);
    if (!p) return;
    setDraft((d) => ({
      ...d,
      sms_provider: p.key,
      sms_api_url: p.api_url,
      sms_http_method: p.http_method,
      sms_body_format: p.body_format,
      sms_body_template: p.body_template,
      sms_auth_header_name: p.auth_header_name ?? "",
      sms_auth_header_value_template: p.auth_header_value_template ?? "",
      sms_success_status_min: p.success_status_min,
      sms_success_status_max: p.success_status_max,
      sms_success_body_contains: p.success_body_contains ?? "",
    }));
  };

  const save = useMutation({
    mutationFn: () => {
      const payload: SmsSettingsUpdate = { ...draft };
      if (!keyTouched) delete payload.sms_api_key;
      const nullable: (keyof SmsSettingsUpdate)[] = [
        "sms_api_url",
        "sms_body_template",
        "sms_auth_header_name",
        "sms_auth_header_value_template",
        "sms_sender",
        "sms_success_body_contains",
      ];
      for (const k of nullable) {
        if (payload[k] === "") (payload as Record<string, unknown>)[k] = null;
      }
      return updateSmsSettings(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sms-settings"] });
      setSavedAt(Date.now());
      setError(null);
      setKeyTouched(false);
    },
    onError: (e: Error) => setError(e.message),
  });

  const test = useMutation({
    mutationFn: () => testSms(testTo, testText),
    onSuccess: (r) => setTestResult(r),
    onError: (e: Error) =>
      setTestResult({
        ok: false,
        http_status: null,
        response_body: null,
        error: e.message,
      }),
  });

  if (isLoading || !data) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const activePreset = presets?.find((p) => p.key === draft.sms_provider);

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
          <h2 className="text-lg font-semibold">SMS gateway</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Generic HTTP webhook with provider presets. Templates use{" "}
            <code>{"{key}"}</code>, <code>{"{sender}"}</code>,{" "}
            <code>{"{destination}"}</code>, <code>{"{content}"}</code> placeholders.
          </p>
        </div>
        <label className="flex shrink-0 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.sms_enabled ?? false}
            onChange={(e) => setDraft((d) => ({ ...d, sms_enabled: e.target.checked }))}
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
        <Field label="Provider preset">
          <select
            value={draft.sms_provider ?? "custom"}
            onChange={(e) => applyPreset(e.target.value)}
            className={inputClass}
          >
            {presets?.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Sender (from)">
          <input
            type="text"
            value={draft.sms_sender ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, sms_sender: e.target.value }))}
            placeholder="NetFleet"
            className={inputClass}
          />
        </Field>
        <Field
          label="API URL"
          hint={activePreset?.notes ?? undefined}
        >
          <input
            type="text"
            value={draft.sms_api_url ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, sms_api_url: e.target.value }))}
            placeholder="https://example.com/sms/send"
            className={`${inputClass} font-mono text-xs`}
          />
        </Field>
        <Field
          label="API key"
          hint={
            data.has_sms_api_key && !keyTouched
              ? "Leave blank to keep the existing key"
              : undefined
          }
        >
          <input
            type="password"
            autoComplete="new-password"
            placeholder={data.has_sms_api_key ? "•••••••• (set)" : ""}
            value={draft.sms_api_key ?? ""}
            onChange={(e) => {
              setDraft((d) => ({ ...d, sms_api_key: e.target.value }));
              setKeyTouched(true);
            }}
            className={inputClass}
          />
        </Field>
        <Field label="HTTP method">
          <select
            value={draft.sms_http_method ?? "POST"}
            onChange={(e) => setDraft((d) => ({ ...d, sms_http_method: e.target.value }))}
            className={inputClass}
          >
            <option value="GET">GET</option>
            <option value="POST">POST</option>
            <option value="PUT">PUT</option>
          </select>
        </Field>
        <Field label="Body format">
          <select
            value={draft.sms_body_format ?? "form"}
            onChange={(e) => setDraft((d) => ({ ...d, sms_body_format: e.target.value }))}
            className={inputClass}
          >
            <option value="query">Query string (in URL)</option>
            <option value="form">Form (application/x-www-form-urlencoded)</option>
            <option value="json">JSON (application/json)</option>
          </select>
        </Field>
        <div className="md:col-span-2">
          <Field
            label="Body template"
            hint="Placeholders: {key} {sender} {destination} {content}"
          >
            <textarea
              rows={3}
              value={draft.sms_body_template ?? ""}
              onChange={(e) =>
                setDraft((d) => ({ ...d, sms_body_template: e.target.value }))
              }
              className={`${inputClass} font-mono text-xs`}
              placeholder='key={key}&destination={destination}&sender={sender}&content={content}'
            />
          </Field>
        </div>
      </div>

      <details className="mt-5 rounded-md border border-border p-4">
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
          Advanced (auth header, success check, timeout)
        </summary>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Auth header name">
            <input
              type="text"
              value={draft.sms_auth_header_name ?? ""}
              onChange={(e) =>
                setDraft((d) => ({ ...d, sms_auth_header_name: e.target.value }))
              }
              placeholder="Authorization"
              className={inputClass}
            />
          </Field>
          <Field label="Auth header value template">
            <input
              type="text"
              value={draft.sms_auth_header_value_template ?? ""}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  sms_auth_header_value_template: e.target.value,
                }))
              }
              placeholder="Bearer {key}"
              className={`${inputClass} font-mono text-xs`}
            />
          </Field>
          <Field label="Success status range">
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={100}
                max={599}
                value={draft.sms_success_status_min ?? 200}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    sms_success_status_min: Number(e.target.value),
                  }))
                }
                className={inputClass}
              />
              <span className="text-muted-foreground">to</span>
              <input
                type="number"
                min={100}
                max={599}
                value={draft.sms_success_status_max ?? 299}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    sms_success_status_max: Number(e.target.value),
                  }))
                }
                className={inputClass}
              />
            </div>
          </Field>
          <Field
            label="Success body must contain (optional)"
            hint="Substring that must appear in the gateway's response body"
          >
            <input
              type="text"
              value={draft.sms_success_body_contains ?? ""}
              onChange={(e) =>
                setDraft((d) => ({ ...d, sms_success_body_contains: e.target.value }))
              }
              placeholder="e.g. Success"
              className={inputClass}
            />
          </Field>
          <Field label="Timeout (seconds)">
            <input
              type="number"
              min={1}
              max={120}
              value={draft.sms_timeout_seconds ?? 10}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  sms_timeout_seconds: Number(e.target.value),
                }))
              }
              className={inputClass}
            />
          </Field>
        </div>
      </details>

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
            type="tel"
            placeholder="+995..."
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
            className="w-44 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <input
            type="text"
            placeholder="message"
            value={testText}
            onChange={(e) => setTestText(e.target.value)}
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
          {testResult.ok ? (
            <>
              Sent. Gateway returned HTTP {testResult.http_status}.{" "}
              {testResult.response_body && (
                <code className="break-all text-xs">{testResult.response_body}</code>
              )}
            </>
          ) : (
            <>
              Failed: {testResult.error}
              {testResult.http_status !== null && (
                <> (HTTP {testResult.http_status})</>
              )}
            </>
          )}
        </div>
      )}
      {data.sms_last_test_at && !testResult && (
        <p className="mt-3 text-xs text-muted-foreground">
          Last test: {new Date(data.sms_last_test_at).toLocaleString()} —{" "}
          {data.sms_last_test_ok ? "ok" : "failed"}
          {data.sms_last_test_message && ` (${data.sms_last_test_message})`}
        </p>
      )}
    </form>
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
