"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { Field } from "@/components/form-field";
import { useToast } from "@/components/toast";
import { fetchMe, updateProfile, type UserPublic } from "@/lib/auth";

export default function ProfilePage() {
  const qc = useQueryClient();
  const toast = useToast();

  const { data: me } = useQuery<UserPublic | null>({
    queryKey: ["me"],
    queryFn: fetchMe,
  });

  const [displayName, setDisplayName] = useState("");
  const [mobile, setMobile] = useState("");

  useEffect(() => {
    if (me) {
      setDisplayName(me.display_name ?? "");
      setMobile(me.mobile_phone ?? "");
    }
  }, [me]);

  const save = useMutation({
    mutationFn: () =>
      updateProfile({
        display_name: displayName.trim() || null,
        mobile_phone: mobile.trim() || null,
      }),
    onSuccess: (next) => {
      qc.setQueryData(["me"], next);
      toast.success("Profile saved");
    },
    onError: (e: Error) => toast.error("Save failed", e.message),
  });

  if (!me) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Your personal NetFleet account. Admin-managed properties (email, role,
        access rights) live on the <span className="font-mono">Users</span> page.
      </p>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
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
                className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
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
                className="block w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring"
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

          <div className="mt-5 rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
            Password change and TOTP enrolment land in P21 Stage 3 — wired
            against this page.
          </div>
        </section>
      </div>
    </div>
  );
}
