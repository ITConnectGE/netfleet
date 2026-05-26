"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import {
  createPppSecret,
  deletePppSecret,
  listPppSecrets,
  resetPppSecretPassword,
  revealPppSecret,
  type PppSecret,
} from "@/lib/vpn";

const SERVICES = ["any", "l2tp", "pptp", "sstp", "ovpn", "pppoe"] as const;
type Tab = "all" | "l2tp" | "pptp" | "sstp" | "ovpn";

export default function DeviceVpnPage() {
  const params = useParams<{ id: string }>();
  const deviceId = params.id;
  const qc = useQueryClient();

  const [tab, setTab] = useState<Tab>("all");
  const [showForm, setShowForm] = useState(false);
  const [revealFor, setRevealFor] = useState<PppSecret | null>(null);
  const [resetFor, setResetFor] = useState<PppSecret | null>(null);

  const { data: secrets, isLoading, error } = useQuery<PppSecret[]>({
    queryKey: ["ppp-secrets", deviceId],
    queryFn: () => listPppSecrets(deviceId),
  });

  const delMut = useMutation({
    mutationFn: (id: string) => deletePppSecret(deviceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ppp-secrets", deviceId] }),
  });

  const filtered = (secrets ?? []).filter((s) =>
    tab === "all" ? true : s.service === tab || s.service === "any",
  );

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">VPN — PPP secrets</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            L2TP, PPTP, SSTP and OpenVPN credentials. Reveal records who saw which secret;
            every change is rotation-logged so the offboarding risk report stays accurate.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New secret"}
        </button>
      </div>

      <div className="mt-4 flex gap-1 border-b border-border">
        {(["all", "l2tp", "pptp", "sstp", "ovpn"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`border-b-2 px-3 py-1.5 text-sm font-medium transition ${
              tab === t
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {(error as Error).message}
        </div>
      )}

      {showForm && (
        <CreateForm
          deviceId={deviceId}
          defaultService={tab === "all" ? "l2tp" : tab}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["ppp-secrets", deviceId] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Service</th>
              <th className="px-4 py-2.5 font-medium">Profile</th>
              <th className="px-4 py-2.5 font-medium">Remote IP</th>
              <th className="px-4 py-2.5 font-medium">Comment</th>
              <th className="px-4 py-2.5 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  No PPP secrets {tab !== "all" && `for ${tab.toUpperCase()}`} yet.
                </td>
              </tr>
            )}
            {filtered.map((s) => (
              <tr key={s.id ?? s.name} className="hover:bg-accent/30">
                <td className="px-4 py-3 font-medium">
                  {s.name}
                  {s.disabled && (
                    <span className="ml-2 rounded-md bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-800">
                      disabled
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-xs">{s.service}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{s.profile ?? "—"}</td>
                <td className="px-4 py-3 font-mono text-xs">{s.remote_address ?? "—"}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{s.comment ?? "—"}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => setRevealFor(s)}
                    className="text-xs text-amber-700 hover:underline"
                    title="Reveal password — audited"
                  >
                    Reveal
                  </button>
                  <button
                    onClick={() => setResetFor(s)}
                    className="ml-3 text-xs text-primary hover:underline"
                  >
                    Reset
                  </button>
                  <button
                    onClick={() => {
                      if (
                        s.id &&
                        confirm(`Delete "${s.name}"? This removes the credential from the device.`)
                      ) {
                        delMut.mutate(s.id);
                      }
                    }}
                    className="ml-3 text-xs text-destructive hover:underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {revealFor?.id && (
        <RevealModal
          deviceId={deviceId}
          secret={revealFor}
          onClose={() => setRevealFor(null)}
        />
      )}
      {resetFor?.id && (
        <ResetModal
          deviceId={deviceId}
          secret={resetFor}
          onClose={() => setResetFor(null)}
        />
      )}
    </div>
  );
}

// ---------------- Create ----------------

function CreateForm({
  deviceId,
  defaultService,
  onCreated,
}: {
  deviceId: string;
  defaultService: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [service, setService] = useState(defaultService);
  const [password, setPassword] = useState("");
  const [profile, setProfile] = useState("");
  const [localAddress, setLocalAddress] = useState("");
  const [remoteAddress, setRemoteAddress] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createPppSecret(deviceId, {
        name,
        service,
        password,
        profile: profile || null,
        local_address: localAddress || null,
        remote_address: remoteAddress || null,
        comment: comment || null,
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!password) {
      setError("Password is required.");
      return;
    }
    m.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="mt-6 rounded-lg border border-border bg-card p-5">
      {error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-3">
        <Field label="Name" htmlFor="v-name">
          <input
            id="v-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="client-alpha"
            autoComplete="off"
          />
        </Field>
        <Field label="Service" htmlFor="v-svc">
          <select
            id="v-svc"
            value={service}
            onChange={(e) => setService(e.target.value)}
            className={input}
          >
            {SERVICES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Profile" htmlFor="v-prof" hint="RouterOS PPP profile name">
          <input
            id="v-prof"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            className={input}
            placeholder="default-encryption"
          />
        </Field>
        <Field label="Password" htmlFor="v-pass">
          <input
            id="v-pass"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={input}
            autoComplete="new-password"
          />
        </Field>
        <Field label="Local address" htmlFor="v-local">
          <input
            id="v-local"
            value={localAddress}
            onChange={(e) => setLocalAddress(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.10.10.1"
          />
        </Field>
        <Field label="Remote address" htmlFor="v-remote">
          <input
            id="v-remote"
            value={remoteAddress}
            onChange={(e) => setRemoteAddress(e.target.value)}
            className={`${input} font-mono`}
            placeholder="10.10.10.20"
          />
        </Field>
        <Field label="Comment" htmlFor="v-comment">
          <input
            id="v-comment"
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
          {m.isPending ? "Creating…" : "Create secret"}
        </button>
      </div>
    </form>
  );
}

// ---------------- Reveal ----------------

function RevealModal({
  deviceId,
  secret,
  onClose,
}: {
  deviceId: string;
  secret: PppSecret;
  onClose: () => void;
}) {
  const [justification, setJustification] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () => revealPppSecret(deviceId, secret.id!, justification),
    onSuccess: (res) => setRevealed(res.password),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Modal title="Reveal password" onClose={onClose}>
      <p className="mt-1 text-xs text-muted-foreground">
        Showing the plaintext password for <strong>{secret.name}</strong> ({secret.service}) is
        recorded in the audit log and in the offboarding risk report.
      </p>

      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {revealed ? (
        <div className="mt-4 space-y-3">
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            This view has been recorded. Rotate this secret once you no longer need it on the user&apos;s screen.
          </div>
          <div className="break-all rounded-md border border-input bg-background p-3 font-mono text-sm">
            {revealed}
          </div>
          <button
            onClick={onClose}
            className="block w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            I&apos;ve copied it — close
          </button>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (!confirmed) {
              setError("Please confirm you understand the audit consequence.");
              return;
            }
            m.mutate();
          }}
          className="mt-4 space-y-3"
        >
          <label className="block space-y-1.5 text-sm font-medium">
            Justification <span className="text-xs font-normal text-muted-foreground">(optional but recommended)</span>
            <textarea
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              rows={2}
              placeholder="e.g. handing off to client; reading to phone support"
              maxLength={1024}
            />
          </label>
          <label className="flex items-start gap-2 text-xs">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="mt-0.5 size-4 rounded"
            />
            <span>
              I understand this reveal will appear in the audit log and in this user&apos;s
              offboarding risk report until the secret is rotated.
            </span>
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={m.isPending}
              className="rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
            >
              {m.isPending ? "Revealing…" : "Reveal password"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

// ---------------- Reset ----------------

function ResetModal({
  deviceId,
  secret,
  onClose,
}: {
  deviceId: string;
  secret: PppSecret;
  onClose: () => void;
}) {
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () => resetPppSecretPassword(deviceId, secret.id!, pw),
    onSuccess: () => setDone(true),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Modal title={`Reset password for ${secret.name}`} onClose={onClose}>
      {error && (
        <div className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}
      {done ? (
        <div className="mt-4 space-y-3">
          <div className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
            Password updated on the device. Past reveals of this secret are now considered rotated.
          </div>
          <button
            onClick={onClose}
            className="block w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Close
          </button>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            if (pw.length < 6) {
              setError("Password must be at least 6 characters.");
              return;
            }
            if (pw !== confirm) {
              setError("Passwords do not match.");
              return;
            }
            m.mutate();
          }}
          className="mt-4 space-y-3"
        >
          <input
            type="password"
            required
            placeholder="new password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            autoComplete="new-password"
          />
          <input
            type="password"
            required
            placeholder="confirm"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            autoComplete="new-password"
          />
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={m.isPending}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {m.isPending ? "Resetting…" : "Reset password"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

// ---------------- shared bits ----------------

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-lg">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
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
