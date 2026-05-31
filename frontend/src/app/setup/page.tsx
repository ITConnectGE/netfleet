"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Logo } from "@/components/logo";
import { fetchSetupStatus, performSetup } from "@/lib/auth";

export default function SetupPage() {
  const router = useRouter();
  const [orgName, setOrgName] = useState("");
  const [orgSlug, setOrgSlug] = useState("");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [tokenFromUrl, setTokenFromUrl] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Read the bootstrap token from the URL fragment if the installer-printed
  // link was used (e.g. https://host/setup#token=…). Fragments are not sent
  // to the server in the initial request, so the token never lands in
  // access logs, the Referer header, or upstream proxy caches.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash;
    if (!hash) return;
    const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
    const t = params.get("token");
    if (t) {
      setBootstrapToken(t);
      setTokenFromUrl(true);
      // Strip the fragment immediately so a stray screen-recording or
      // address-bar glance doesn't leak it.
      history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  useEffect(() => {
    fetchSetupStatus()
      .then((s) => {
        if (s.setup_complete) router.replace("/login");
      })
      .catch(() => {});
  }, [router]);

  // Auto-derive slug from org name
  useEffect(() => {
    if (!orgSlug || orgSlug === slugify(orgName.slice(0, -1))) {
      setOrgSlug(slugify(orgName));
    }
  }, [orgName, orgSlug]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (!bootstrapToken.trim()) {
      setError(
        "Bootstrap token is required. Use the URL printed by install.sh, " +
          "or paste the value of NETFLEET_BOOTSTRAP_TOKEN from /opt/netfleet/.env.",
      );
      return;
    }
    setSubmitting(true);
    try {
      await performSetup(
        {
          organization_name: orgName,
          organization_slug: orgSlug,
          admin_email: email,
          admin_display_name: displayName,
          admin_password: password,
        },
        bootstrapToken.trim(),
      );
      router.replace("/login?setup=complete");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 via-white to-emerald-50 p-6 dark:from-slate-950 dark:via-background dark:to-slate-900">
      <div className="w-full max-w-md">
        <div className="mb-6 flex justify-center">
          <Logo size={40} />
        </div>
        <div className="rounded-2xl border border-border bg-card p-8 shadow-sm">
          <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            First-run setup
          </div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome to NetFleet</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Let&apos;s create your organization and the first admin user.
        </p>

        {error && (
          <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <h2 className="text-sm font-medium text-muted-foreground">Bootstrap</h2>
          <Field
            label="Setup token"
            htmlFor="bootstrap-token"
            hint={
              tokenFromUrl
                ? "loaded from the install URL"
                : "value of NETFLEET_BOOTSTRAP_TOKEN in /opt/netfleet/.env"
            }
          >
            <input
              id="bootstrap-token"
              type="password"
              required
              value={bootstrapToken}
              onChange={(e) => setBootstrapToken(e.target.value)}
              className={`${inputClass} font-mono`}
              autoComplete="off"
              spellCheck={false}
              placeholder="64-char hex token from install.sh"
            />
          </Field>

          <hr className="border-border" />

          <h2 className="text-sm font-medium text-muted-foreground">Organization</h2>
          <Field label="Name" htmlFor="org-name">
            <input
              id="org-name"
              required
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              className={inputClass}
              placeholder="ITConnectGE"
            />
          </Field>
          <Field label="Slug" htmlFor="org-slug" hint="used in URLs and audit log">
            <input
              id="org-slug"
              required
              pattern="^[a-z0-9][-a-z0-9]*[a-z0-9]$"
              minLength={2}
              maxLength={63}
              value={orgSlug}
              onChange={(e) => setOrgSlug(e.target.value.toLowerCase())}
              className={`${inputClass} font-mono`}
              placeholder="itconnectge"
            />
          </Field>

          <hr className="border-border" />

          <h2 className="text-sm font-medium text-muted-foreground">Admin user</h2>
          <Field label="Display name" htmlFor="admin-name">
            <input
              id="admin-name"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className={inputClass}
              placeholder="Dimitri Katsarava"
            />
          </Field>
          <Field label="Email" htmlFor="admin-email">
            <input
              id="admin-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              placeholder="admin@itconnect.ge"
              autoComplete="email"
            />
          </Field>
          <Field label="Password" htmlFor="admin-password" hint="at least 12 characters">
            <input
              id="admin-password"
              type="password"
              required
              minLength={12}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
              autoComplete="new-password"
            />
          </Field>
          <Field label="Confirm password" htmlFor="admin-confirm">
            <input
              id="admin-confirm"
              type="password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className={inputClass}
              autoComplete="new-password"
            />
          </Field>

          <button type="submit" disabled={submitting} className={primaryBtnClass}>
            {submitting ? "Creating…" : "Create organization"}
          </button>
        </form>
        </div>
      </div>
    </main>
  );
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
const primaryBtnClass =
  "block w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50";

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
