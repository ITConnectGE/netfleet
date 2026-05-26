"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { fetchSetupStatus, login, verifyTotp } from "@/lib/auth";

type Phase = "password" | "totp";

export default function LoginPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("password");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfaTempToken, setMfaTempToken] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // If the system isn't set up yet, send the user to the setup wizard.
  useEffect(() => {
    fetchSetupStatus()
      .then((s) => {
        if (!s.setup_complete) router.replace("/setup");
      })
      .catch(() => {});
  }, [router]);

  async function onSubmitPassword(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.status === "mfa_required") {
        setMfaTempToken(result.mfa_temp_token);
        setPhase("totp");
      } else {
        router.replace("/dashboard");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function onSubmitTotp(e: FormEvent) {
    e.preventDefault();
    if (!mfaTempToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await verifyTotp(mfaTempToken, code);
      router.replace("/dashboard");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-8 shadow-sm">
        <h1 className="text-2xl font-semibold tracking-tight">
          {phase === "password" ? "Sign in" : "Two-factor"}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {phase === "password"
            ? "Local credentials or Microsoft single sign-on."
            : `Enter the 6-digit code from your authenticator app.`}
        </p>

        {error && (
          <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {phase === "password" ? (
          <form className="mt-6 space-y-4" onSubmit={onSubmitPassword}>
            <Field label="Email" htmlFor="email">
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputClass}
                placeholder="you@itconnectge.ge"
                autoComplete="email"
              />
            </Field>
            <Field label="Password" htmlFor="password">
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClass}
                autoComplete="current-password"
              />
            </Field>
            <button type="submit" disabled={submitting} className={primaryBtnClass}>
              {submitting ? "Signing inâ€¦" : "Sign in"}
            </button>
          </form>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={onSubmitTotp}>
            <Field label="Authenticator code" htmlFor="totp">
              <input
                id="totp"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={8}
                required
                autoFocus
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                className={`${inputClass} tracking-[0.5em] text-center text-lg`}
                placeholder="000000"
              />
            </Field>
            <button type="submit" disabled={submitting} className={primaryBtnClass}>
              {submitting ? "Verifyingâ€¦" : "Verify"}
            </button>
            <button
              type="button"
              onClick={() => {
                setPhase("password");
                setCode("");
                setMfaTempToken(null);
              }}
              className="block w-full text-center text-xs text-muted-foreground hover:underline"
            >
              â† Use a different account
            </button>
          </form>
        )}

        <div className="my-6 flex items-center gap-3">
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs text-muted-foreground">or</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <a
          href="/api/v1/auth/oidc/start"
          className="flex w-full items-center justify-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium transition hover:bg-accent"
        >
          Continue with Microsoft
        </a>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          <Link href="/" className="underline-offset-4 hover:underline">
            â† Back to landing
          </Link>
        </p>
      </div>
    </main>
  );
}

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
const primaryBtnClass =
  "block w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50";

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
    </div>
  );
}
