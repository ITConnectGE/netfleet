"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Field } from "@/components/form-field";
import { useToast } from "@/components/toast";
import {
  changePassword,
  disableTotp,
  enrollTotpBegin,
  enrollTotpConfirm,
  fetchMe,
  updateProfile,
  type TotpEnrollResponse,
  type UserPublic,
} from "@/lib/auth";

export default function ProfilePage() {
  const qc = useQueryClient();
  const toast = useToast();
  const searchParams = useSearchParams();
  const forcePassword = searchParams.get("force") === "password";

  const { data: me } = useQuery<UserPublic | null>({
    queryKey: ["me"],
    queryFn: fetchMe,
  });

  if (!me) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const mustChange = me.must_change_password;
  // When the user is being walked through a forced password change we
  // hide everything else, so the only available next action is to
  // change their password. The layout already keeps them on this page.
  const lockedToPassword = mustChange || forcePassword;

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Your personal NetFleet account. Admin-managed properties (email, role,
        access rights) live on the <span className="font-mono">Users</span> page.
      </p>

      {mustChange && (
        <div className="mt-4 rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong>Set your password to continue.</strong> The temporary password
          you signed in with cannot be reused. Once you change it, the rest of
          NetFleet unlocks.
        </div>
      )}

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        {!lockedToPassword && (
          <IdentitySection
            me={me}
            onSaved={(next) => qc.setQueryData(["me"], next)}
            toastSuccess={(t, b) => toast.success(t, b)}
            toastError={(t, b) => toast.error(t, b)}
          />
        )}

        <PasswordSection
          // After a successful change we expect /auth/me to flip
          // must_change_password to false; invalidate so the gate
          // unlocks on its own.
          onChanged={() => qc.invalidateQueries({ queryKey: ["me"] })}
          forced={mustChange}
        />

        {!lockedToPassword && (
          <TotpSection
            me={me}
            onChanged={() => qc.invalidateQueries({ queryKey: ["me"] })}
          />
        )}

        {!lockedToPassword && (
          <OtpLoginSection
            me={me}
            onChanged={(next) => qc.setQueryData(["me"], next)}
          />
        )}

        {!lockedToPassword && <AccountSection me={me} />}
      </div>
    </div>
  );
}

// ---------------- Identity ----------------

function IdentitySection({
  me,
  onSaved,
  toastSuccess,
  toastError,
}: {
  me: UserPublic;
  onSaved: (next: UserPublic) => void;
  toastSuccess: (title: string, body?: string) => void;
  toastError: (title: string, body?: string) => void;
}) {
  const [displayName, setDisplayName] = useState(me.display_name ?? "");
  const [mobile, setMobile] = useState(me.mobile_phone ?? "");

  useEffect(() => {
    setDisplayName(me.display_name ?? "");
    setMobile(me.mobile_phone ?? "");
  }, [me]);

  const save = useMutation({
    mutationFn: () =>
      updateProfile({
        display_name: displayName.trim() || null,
        mobile_phone: mobile.trim() || null,
      }),
    onSuccess: (next) => {
      onSaved(next);
      toastSuccess("Profile saved");
    },
    onError: (e: Error) => toastError("Save failed", e.message),
  });

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-sm font-medium text-muted-foreground">Identity</h2>
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
        className="mt-3 space-y-4"
      >
        <Field label="Email" example="Contact an admin to change">
          <input
            value={me.email}
            disabled
            className="block w-full cursor-not-allowed rounded-md border border-input bg-muted px-3 py-2 text-sm text-muted-foreground"
          />
        </Field>
        <Field label="Display name" htmlFor="pn-name">
          <input
            id="pn-name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className={INPUT}
          />
        </Field>
        <Field
          label="Mobile phone"
          htmlFor="pn-mobile"
          tooltip="Used for SMS one-time codes when you sign in, and as an extra contact when other operators need to reach you."
          example="International format (e.g. +995 555 12 34 56)"
        >
          <input
            id="pn-mobile"
            type="tel"
            value={mobile}
            onChange={(e) => setMobile(e.target.value)}
            className={`${INPUT} font-mono`}
          />
        </Field>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={save.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- Password ----------------

function PasswordSection({
  forced,
  onChanged,
}: {
  forced: boolean;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      changePassword({ current_password: current, new_password: next }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success("Password changed", "Check your email for confirmation.");
      onChanged();
    },
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (next.length < 12) {
      setError("New password must be at least 12 characters.");
      return;
    }
    if (next !== confirm) {
      setError("New passwords do not match.");
      return;
    }
    if (current === next) {
      setError("New password must differ from current password.");
      return;
    }
    m.mutate();
  }

  return (
    <section
      className={
        forced
          ? "rounded-lg border-2 border-primary/40 bg-card p-5 md:col-span-2"
          : "rounded-lg border border-border bg-card p-5"
      }
    >
      <h2 className="text-sm font-medium text-muted-foreground">
        {forced ? "Set a new password" : "Change password"}
      </h2>
      <p className="mt-1 text-xs text-muted-foreground">
        You will receive an email confirmation. Active sessions on other
        devices will be signed out.
      </p>
      <form onSubmit={onSubmit} className="mt-3 space-y-3">
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}
        <Field label="Current password" htmlFor="pw-cur">
          <input
            id="pw-cur"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className={INPUT}
          />
        </Field>
        <Field
          label="New password"
          htmlFor="pw-new"
          example="Minimum 12 characters; mix in numbers and symbols"
        >
          <input
            id="pw-new"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            className={INPUT}
          />
        </Field>
        <Field label="Confirm new password" htmlFor="pw-conf">
          <input
            id="pw-conf"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={INPUT}
          />
        </Field>
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={m.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {m.isPending ? "Updating…" : "Update password"}
          </button>
        </div>
      </form>
    </section>
  );
}

// ---------------- TOTP ----------------

function TotpSection({
  me,
  onChanged,
}: {
  me: UserPublic;
  onChanged: () => void;
}) {
  const toast = useToast();
  const [enrolment, setEnrolment] = useState<TotpEnrollResponse | null>(null);
  const [code, setCode] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const begin = useMutation({
    mutationFn: enrollTotpBegin,
    onSuccess: (res) => {
      setEnrolment(res);
      setError(null);
    },
    onError: (e: Error) => setError(e.message),
  });
  const confirm = useMutation({
    mutationFn: () => enrollTotpConfirm(code),
    onSuccess: () => {
      setEnrolment(null);
      setCode("");
      toast.success("Two-factor enabled");
      onChanged();
    },
    onError: (e: Error) => setError(e.message),
  });
  const remove = useMutation({
    mutationFn: () => disableTotp(disablePassword),
    onSuccess: () => {
      setDisablePassword("");
      toast.success("Two-factor disabled");
      onChanged();
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-sm font-medium text-muted-foreground">
        Two-factor authentication
      </h2>
      <p className="mt-1 text-xs text-muted-foreground">
        Time-based one-time codes (TOTP) from Google Authenticator, 1Password,
        Bitwarden, …
      </p>

      {error && (
        <p className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}

      {!me.totp_enrolled && !enrolment && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => {
              setError(null);
              begin.mutate();
            }}
            disabled={begin.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {begin.isPending ? "Generating…" : "Enable TOTP"}
          </button>
        </div>
      )}

      {enrolment && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            confirm.mutate();
          }}
          className="mt-4 space-y-3"
        >
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Scan this QR code (or paste the secret) in your authenticator app,
            then enter the 6-digit code it shows to confirm.
          </div>
          <div className="flex flex-col items-start gap-3 md:flex-row md:items-center">
            <img
              alt="TOTP QR code"
              src={`https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(
                enrolment.otpauth_uri,
              )}`}
              className="size-44 rounded-md border border-border bg-white p-1"
            />
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">
                Secret (manual entry)
              </div>
              <code className="block break-all rounded-md bg-muted px-2 py-1 font-mono text-[11px]">
                {enrolment.secret}
              </code>
            </div>
          </div>
          <Field label="Verification code" htmlFor="totp-code">
            <input
              id="totp-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              pattern="\d{6,8}"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className={`${INPUT} font-mono tracking-widest`}
              placeholder="123456"
            />
          </Field>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setEnrolment(null);
                setCode("");
              }}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={confirm.isPending}
              className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {confirm.isPending ? "Verifying…" : "Confirm"}
            </button>
          </div>
        </form>
      )}

      {me.totp_enrolled && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (!disablePassword) {
              setError("Re-enter your password to disable TOTP.");
              return;
            }
            remove.mutate();
          }}
          className="mt-4 space-y-3"
        >
          <p className="text-xs text-emerald-700">
            TOTP is enrolled. To remove it, confirm your password.
          </p>
          <Field label="Current password" htmlFor="totp-pw">
            <input
              id="totp-pw"
              type="password"
              autoComplete="current-password"
              value={disablePassword}
              onChange={(e) => setDisablePassword(e.target.value)}
              className={INPUT}
            />
          </Field>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={remove.isPending}
              className="rounded-md border border-destructive/40 bg-background px-3 py-1.5 text-sm font-medium text-destructive transition hover:bg-destructive/10 disabled:opacity-50"
            >
              {remove.isPending ? "Disabling…" : "Disable TOTP"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

// ---------------- OTP at login ----------------

function OtpLoginSection({
  me,
  onChanged,
}: {
  me: UserPublic;
  onChanged: (next: UserPublic) => void;
}) {
  const toast = useToast();
  const [enabled, setEnabled] = useState(me.otp_login_enabled);
  // TOTP takes priority — the backend short-circuits this branch when
  // TOTP is enrolled. Surface that so the toggle doesn't look broken.
  const supersededByTotp = me.totp_enrolled;

  useEffect(() => {
    setEnabled(me.otp_login_enabled);
  }, [me.otp_login_enabled]);

  const save = useMutation({
    mutationFn: () => updateProfile({ otp_login_enabled: enabled }),
    onSuccess: (next) => {
      onChanged(next);
      toast.success(
        enabled ? "One-time login code enabled" : "One-time login code disabled",
      );
    },
    onError: (e: Error) => toast.error("Save failed", e.message),
  });

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-sm font-medium text-muted-foreground">
        One-time code at login
      </h2>
      <p className="mt-1 text-xs text-muted-foreground">
        When you sign in, NetFleet will send a 6-digit code by SMS (if your
        mobile is set and the org gateway is configured) or by email.
      </p>

      {supersededByTotp && (
        <p className="mt-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-[11px] text-amber-900">
          You have TOTP enabled — it always takes precedence, so the one-time
          code only kicks in if you remove TOTP.
        </p>
      )}

      <label className="mt-4 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          className="size-4 rounded"
        />
        Require a one-time code at every login
      </label>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending || enabled === me.otp_login_enabled}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </section>
  );
}

// ---------------- Account meta ----------------

function AccountSection({ me }: { me: UserPublic }) {
  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <h2 className="text-sm font-medium text-muted-foreground">Account</h2>
      <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
        <dt className="text-muted-foreground">Role</dt>
        <dd>{me.is_admin ? "Admin" : "Member"}</dd>

        <dt className="text-muted-foreground">Auth method</dt>
        <dd className="font-mono">{me.auth_method}</dd>

        <dt className="text-muted-foreground">Two-factor</dt>
        <dd>
          {me.totp_enrolled ? (
            <span className="text-emerald-700">enrolled</span>
          ) : (
            <span className="text-muted-foreground">not enrolled</span>
          )}
        </dd>
      </dl>
    </section>
  );
}

const INPUT =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";
