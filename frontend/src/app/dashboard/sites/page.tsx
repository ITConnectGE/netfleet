"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { createSite, listSites, type Site } from "@/lib/sites";

export default function SitesPage() {
  const qc = useQueryClient();
  const { data: sites, isLoading } = useQuery<Site[]>({
    queryKey: ["sites"],
    queryFn: listSites,
  });
  const [showForm, setShowForm] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sites</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            One site per MSP client. Devices are grouped under sites.
          </p>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          {showForm ? "Cancel" : "+ New site"}
        </button>
      </div>

      {showForm && (
        <SiteForm
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["sites"] });
            setShowForm(false);
          }}
        />
      )}

      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Slug</th>
              <th className="px-4 py-2.5 font-medium">Devices</th>
              <th className="px-4 py-2.5 font-medium">Contact</th>
              <th className="px-4 py-2.5 font-medium">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && (!sites || sites.length === 0) && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">
                  No sites yet. Click <strong>+ New site</strong> to create one.
                </td>
              </tr>
            )}
            {sites?.map((s) => (
              <tr key={s.id} className="hover:bg-accent/30">
                <td className="px-4 py-3 font-medium">
                  <Link href={`/dashboard/sites/${s.id}`} className="hover:underline">
                    {s.name}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{s.slug}</td>
                <td className="px-4 py-3">{s.device_count}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {s.contact_email ?? "—"}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {new Date(s.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SiteForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [address, setAddress] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () =>
      createSite({
        name,
        slug,
        address: address || null,
        contact_email: contactEmail || null,
        contact_phone: contactPhone || null,
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
        <div className="space-y-1.5">
          <label htmlFor="s-name" className="text-sm font-medium">
            Name
          </label>
          <input
            id="s-name"
            required
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!slug) {
                setSlug(slugify(e.target.value));
              }
            }}
            className={inputClass}
            placeholder="Client A"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="s-slug" className="text-sm font-medium">
            Slug
          </label>
          <input
            id="s-slug"
            required
            pattern="^[a-z0-9][-a-z0-9]*[a-z0-9]$"
            minLength={2}
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase())}
            className={`${inputClass} font-mono`}
            placeholder="client-a"
          />
        </div>
        <div className="space-y-1.5 md:col-span-2">
          <label htmlFor="s-address" className="text-sm font-medium">
            Address
          </label>
          <input
            id="s-address"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className={inputClass}
            placeholder="optional"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="s-email" className="text-sm font-medium">
            Contact email
          </label>
          <input
            id="s-email"
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
            className={inputClass}
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="s-phone" className="text-sm font-medium">
            Contact phone
          </label>
          <input
            id="s-phone"
            value={contactPhone}
            onChange={(e) => setContactPhone(e.target.value)}
            className={inputClass}
          />
        </div>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="submit"
          disabled={m.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
        >
          {m.isPending ? "Creating…" : "Create site"}
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

const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";
