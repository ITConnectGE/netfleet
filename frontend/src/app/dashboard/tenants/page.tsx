"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { createTenant, listTenants, type Tenant } from "@/lib/tenants";

export default function TenantsPage() {
  const qc = useQueryClient();
  const { data: tenants, isLoading } = useQuery<Tenant[]>({
    queryKey: ["tenants"],
    queryFn: listTenants,
  });
  const [showForm, setShowForm] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tenants</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your MSP clients. Each tenant can have many sites, and each site many devices.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New tenant"}
        </button>
      </div>

      {showForm && (
        <TenantForm
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["tenants"] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {isLoading && (
          <p className="col-span-full text-sm text-muted-foreground">Loading…</p>
        )}
        {!isLoading && (!tenants || tenants.length === 0) && (
          <p className="col-span-full rounded-lg border border-dashed border-border bg-card p-8 text-center text-sm text-muted-foreground">
            No tenants yet. Click <strong>+ New tenant</strong> to create your first.
          </p>
        )}
        {tenants?.map((t) => (
          <Link
            key={t.id}
            href={`/dashboard/tenants/${t.id}`}
            className="block rounded-lg border border-border bg-card p-5 transition hover:border-primary/40"
          >
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-base font-semibold">{t.name}</h3>
              </div>
              <div className="text-right text-xs text-muted-foreground">
                <div>
                  <span className="font-semibold text-foreground">{t.site_count}</span> site
                  {t.site_count === 1 ? "" : "s"}
                </div>
                <div>
                  <span className="font-semibold text-foreground">{t.device_count}</span>{" "}
                  device{t.device_count === 1 ? "" : "s"}
                </div>
              </div>
            </div>
            {t.description && (
              <p className="mt-3 line-clamp-2 text-xs text-muted-foreground">
                {t.description}
              </p>
            )}
            {t.primary_contact_email && (
              <p className="mt-3 text-xs text-muted-foreground">
                Contact: {t.primary_contact_name ?? t.primary_contact_email}
              </p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}

function TenantForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createTenant({
        name,
        // Slug is a routing/audit identifier the backend still requires;
        // derive it silently from the name. If the operator wants a custom
        // one they can edit it post-create from the tenant detail page —
        // most don't care, so it's no longer in the form.
        slug: slugify(name),
        description: description || null,
        primary_contact_name: contactName || null,
        primary_contact_email: contactEmail || null,
        primary_contact_phone: contactPhone || null,
      }),
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    m.mutate();
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mt-6 rounded-lg border border-border bg-card p-5"
    >
      {error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Name" htmlFor="t-name">
          <input
            id="t-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={input}
            placeholder="Acme Manufacturing"
          />
        </Field>
        <Field label="Description" htmlFor="t-desc">
          <input
            id="t-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={input}
            placeholder="optional"
          />
        </Field>
        <Field label="Primary contact name" htmlFor="t-cname">
          <input
            id="t-cname"
            value={contactName}
            onChange={(e) => setContactName(e.target.value)}
            className={input}
          />
        </Field>
        <Field label="Contact email" htmlFor="t-cemail">
          <input
            id="t-cemail"
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
            className={input}
          />
        </Field>
        <Field label="Contact phone" htmlFor="t-cphone">
          <input
            id="t-cphone"
            value={contactPhone}
            onChange={(e) => setContactPhone(e.target.value)}
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
          {m.isPending ? "Creating…" : "Create tenant"}
        </button>
      </div>
    </form>
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

const input =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
