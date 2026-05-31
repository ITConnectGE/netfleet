"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { Logo } from "@/components/logo";
import {
  fetchSetupStatus,
  login,
  sendOtpCode,
  verifyLoginOtp,
  verifyTotp,
  type MfaMethod,
} from "@/lib/auth";

type Phase = "password" | "choose" | "totp" | "otp";

interface OtpInfo {
  channel: "sms" | "email";
  destinationHint: string;
}

export default function LoginPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>("password");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfaTempToken, setMfaTempToken] = useState<string | null>(null);
  const [otpInfo, setOtpInfo] = useState<OtpInfo | null>(null);
  const [methods, setMethods] = useState<MfaMethod[]>([]);
  const [defaultMethod, setDefaultMethod] = useState<"totp" | "email" | "sms">(
    "totp",
  );

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
      if (result.status === "mfa_choice") {
        setMfaTempToken(result.mfa_temp_token);
        setMethods(result.methods);
        setDefaultMethod(result.default_method);
        setPhase("choose");
      } else if (result.status === "mfa_required") {
        setMfaTempToken(result.mfa_temp_token);
        setPhase("totp");
      } else if (result.status === "otp_required") {
        setMfaTempToken(result.mfa_temp_token);
        setOtpInfo({
          channel: result.channel,
          destinationHint: result.destination_hint,
        });
        setPhase("otp");
      } else {
        router.replace("/dashboard");
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function pickMethod(m: "totp" | "email" | "sms") {
    if (!mfaTempToken) return;
    setError(null);
    if (m === "totp") {
      setPhase("totp");
      return;
    }
    // email / sms: ask the server to dispatch the code, then move on.
    setSubmitting(true);
    try {
      const res = await sendOtpCode(mfaTempToken, m);
      setOtpInfo({ channel: res.method, destinationHint: res.destination_hint });
      setPhase("otp");
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

  async function onSubmitOtp(e: FormEvent) {
    e.preventDefault();
    if (!mfaTempToken) return;
    setError(null);
    setSubmitting(true);
    try {
      await verifyLoginOtp(mfaTempToken, code);
      router.replace("/dashboard");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function resetToPassword() {
    setPhase("password");
    setCode("");
    setMfaTempToken(null);
    setOtpInfo(null);
    setMethods([]);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 via-white to-emerald-50 p-6 dark:from-slate-950 dark:via-background dark:to-slate-900">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center text-center">
          <Logo size={48} showWordmark={false} />
          <h1 className="mt-3 text-2xl font-semibold tracking-tight">NetFleet</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Multi-vendor network fleet management for MSPs
          </p>
        </div>

        <div className="rounded-2xl border border-border bg-card p-8 shadow-sm">
          <h2 className="text-xl font-semibold tracking-tight">
            {phase === "password"
              ? "Sign in"
              : phase === "choose"
                ? "Choose a second factor"
                : phase === "totp"
                  ? "Two-factor authentication"
                  : "One-time code"}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {phase === "password"
              ? "Local credentials or Microsoft single sign-on."
              : phase === "choose"
                ? "Pick the channel you'd like to use. TOTP is the fastest; email and SMS arrive in about a minute."
                : phase === "totp"
                  ? "Enter the 6-digit code from your authenticator app."
                  : otpInfo
                    ? `We sent a code via ${otpInfo.channel === "sms" ? "SMS" : "email"} to ${otpInfo.destinationHint}. It expires in 5 minutes.`
                    : "Enter the code we just sent you."}
          </p>

          {error && (
            <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {phase === "password" && (
            <form className="mt-6 space-y-4" onSubmit={onSubmitPassword}>
              <Field label="Email" htmlFor="email">
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={inputClass}
                  placeholder="you@itconnect.ge"
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
                {submitting ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}

          {phase === "choose" && (
            <div className="mt-6 space-y-2">
              {methods.map((m) => (
                <button
                  key={m.method}
                  type="button"
                  onClick={() => pickMethod(m.method)}
                  disabled={submitting}
                  className={`flex w-full items-center justify-between rounded-md border px-3 py-2.5 text-left text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${
                    m.method === defaultMethod
                      ? "border-primary bg-primary/5 hover:bg-primary/10"
                      : "border-input bg-background hover:bg-accent"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <MethodIcon method={m.method} />
                    <div>
                      <div className="font-medium">{methodLabel(m.method)}</div>
                      {m.destination_hint && (
                        <div className="text-[11px] text-muted-foreground">
                          {m.destination_hint}
                        </div>
                      )}
                    </div>
                  </div>
                  {m.method === defaultMethod && (
                    <span className="rounded-md bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary">
                      recommended
                    </span>
                  )}
                </button>
              ))}
              <button
                type="button"
                onClick={resetToPassword}
                className="block w-full pt-2 text-center text-xs text-muted-foreground hover:underline"
              >
                ← Use a different account
              </button>
            </div>
          )}

          {phase === "totp" && (
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
                  className={`${inputClass} text-center text-lg tracking-[0.5em]`}
                  placeholder="000000"
                />
              </Field>
              <button type="submit" disabled={submitting} className={primaryBtnClass}>
                {submitting ? "Verifying…" : "Verify"}
              </button>
              {methods.length > 1 && (
                <button
                  type="button"
                  onClick={() => {
                    setCode("");
                    setPhase("choose");
                  }}
                  className="block w-full text-center text-xs text-muted-foreground hover:underline"
                >
                  Use a different factor
                </button>
              )}
              <button
                type="button"
                onClick={resetToPassword}
                className="block w-full text-center text-xs text-muted-foreground hover:underline"
              >
                ← Use a different account
              </button>
            </form>
          )}

          {phase === "otp" && (
            <form className="mt-6 space-y-4" onSubmit={onSubmitOtp}>
              <Field label="One-time code" htmlFor="otp">
                <input
                  id="otp"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={8}
                  required
                  autoFocus
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  className={`${inputClass} text-center text-lg tracking-[0.5em]`}
                  placeholder="000000"
                  autoComplete="one-time-code"
                />
              </Field>
              <button type="submit" disabled={submitting} className={primaryBtnClass}>
                {submitting ? "Verifying…" : "Verify"}
              </button>
              {methods.length > 1 && (
                <button
                  type="button"
                  onClick={() => {
                    setCode("");
                    setPhase("choose");
                  }}
                  className="block w-full text-center text-xs text-muted-foreground hover:underline"
                >
                  Use a different factor
                </button>
              )}
              <button
                type="button"
                onClick={resetToPassword}
                className="block w-full text-center text-xs text-muted-foreground hover:underline"
              >
                ← Use a different account
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
            <MicrosoftLogo className="size-4" />
            Continue with Microsoft
          </a>
        </div>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          <Link href="/" className="underline-offset-4 hover:underline">
            ← Back to landing
          </Link>
        </p>
      </div>
    </main>
  );
}

function methodLabel(m: "totp" | "email" | "sms"): string {
  if (m === "totp") return "Authenticator app (TOTP)";
  if (m === "email") return "Email a code";
  return "Text a code (SMS)";
}

function MethodIcon({ method }: { method: "totp" | "email" | "sms" }) {
  const cls = "size-5 shrink-0 text-muted-foreground";
  if (method === "totp") {
    return (
      <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="4" y="2" width="16" height="20" rx="2" />
        <path d="M12 14v.01" />
        <path d="M8 18h8" />
      </svg>
    );
  }
  if (method === "email") {
    return (
      <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="3" y="5" width="18" height="14" rx="2" />
        <path d="m3 7 9 6 9-6" />
      </svg>
    );
  }
  return (
    <svg className={cls} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="7" y="2" width="10" height="20" rx="2" />
      <path d="M11 18h2" />
    </svg>
  );
}

function MicrosoftLogo(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 23 23" xmlns="http://www.w3.org/2000/svg" {...props}>
      <rect x="1" y="1" width="10" height="10" fill="#f25022" />
      <rect x="12" y="1" width="10" height="10" fill="#7fba00" />
      <rect x="1" y="12" width="10" height="10" fill="#00a4ef" />
      <rect x="12" y="12" width="10" height="10" fill="#ffb900" />
    </svg>
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
