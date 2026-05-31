"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import {
  createSite,
  deleteSite,
  listSites,
  type Site,
  type SiteCreate,
} from "@/lib/sites";
import { deleteTenant, getTenant, type Tenant } from "@/lib/tenants";

const SiteLocationPicker = dynamic(
  () => import("@/components/site-location-picker"),
  { ssr: false, loading: () => <div className="h-72 animate-pulse rounded-md bg-muted" /> },
);

export default function TenantDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const tenantId = params.id;
  const qc = useQueryClient();

  const { data: tenant, isLoading } = useQuery<Tenant>({
    queryKey: ["tenant", tenantId],
    queryFn: () => getTenant(tenantId),
  });
  const { data: sites } = useQuery<Site[]>({
    queryKey: ["sites", tenantId],
    queryFn: () => listSites(tenantId),
  });

  const [showSiteForm, setShowSiteForm] = useState(false);

  const delTenantMut = useMutation({
    mutationFn: () => deleteTenant(tenantId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenants"] });
      router.replace("/dashboard/tenants");
    },
  });
  const delSiteMut = useMutation({
    mutationFn: (id: string) => deleteSite(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sites", tenantId] });
      qc.invalidateQueries({ queryKey: ["tenant", tenantId] });
    },
  });

  if (isLoading || !tenant) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div>
      <Link
        href="/dashboard/tenants"
        className="text-xs text-muted-foreground hover:underline"
      >
        ← Tenants
      </Link>
      <div className="mt-1 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{tenant.name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-mono">{tenant.slug}</span>
            {tenant.primary_contact_email && (
              <>
                {" · "}
                Contact: {tenant.primary_contact_name ?? tenant.primary_contact_email}
              </>
            )}
          </p>
        </div>
        <button
          onClick={() => {
            if (
              confirm(
                `Delete tenant "${tenant.name}"? This will also delete all its sites and devices.`,
              )
            ) {
              delTenantMut.mutate();
            }
          }}
          className="rounded-md border border-destructive/40 bg-background px-3 py-1.5 text-sm font-medium text-destructive transition hover:bg-destructive/10"
        >
          Delete tenant
        </button>
      </div>

      {tenant.description && (
        <p className="mt-3 max-w-3xl text-sm text-muted-foreground">{tenant.description}</p>
      )}

      <div className="mt-10 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Sites</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Physical locations of this tenant.
          </p>
        </div>
        <button
          onClick={() => setShowSiteForm((s) => !s)}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          {showSiteForm ? "Cancel" : "+ New site"}
        </button>
      </div>

      {showSiteForm && (
        <SiteForm
          tenantId={tenantId}
          onCreated={() => {
            qc.invalidateQueries({ queryKey: ["sites", tenantId] });
            qc.invalidateQueries({ queryKey: ["tenant", tenantId] });
            setShowSiteForm(false);
          }}
        />
      )}

      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr className="text-left">
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Slug</th>
              <th className="px-4 py-2.5 font-medium">Devices</th>
              <th className="px-4 py-2.5 font-medium">Address</th>
              <th className="px-4 py-2.5 font-medium">Contact</th>
              <th className="px-4 py-2.5 font-medium text-right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {(!sites || sites.length === 0) && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  No sites yet for this tenant.
                </td>
              </tr>
            )}
            {sites?.map((s) => (
              <tr key={s.id} className="hover:bg-accent/30">
                <td className="px-4 py-3 font-medium">
                  <Link
                    href={`/dashboard/sites/${s.id}`}
                    className="text-primary hover:underline"
                  >
                    {s.name}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                  {s.slug}
                </td>
                <td className="px-4 py-3">{s.device_count}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {s.address ?? "—"}
                </td>
                <td className="px-4 py-3 text-xs text-muted-foreground">
                  {s.contact_email ?? "—"}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/dashboard/sites/${s.id}`}
                    className="mr-3 text-xs text-primary hover:underline"
                  >
                    Edit
                  </Link>
                  <button
                    onClick={() => {
                      if (
                        confirm(
                          `Delete site "${s.name}"? This removes the site and its devices.`,
                        )
                      ) {
                        delSiteMut.mutate(s.id);
                      }
                    }}
                    className="text-xs text-destructive hover:underline"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SiteForm({
  tenantId,
  onCreated,
}: {
  tenantId: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [address, setAddress] = useState("");
  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [error, setError] = useState<string | null>(null);

  const m = useMutation({
    mutationFn: () => {
      const payload: SiteCreate = {
        tenant_id: tenantId,
        name,
        slug,
        address: address || null,
        latitude,
        longitude,
        contact_email: contactEmail || null,
        contact_phone: contactPhone || null,
      };
      return createSite(payload);
    },
    onSuccess: () => onCreated(),
    onError: (e: Error) => setError(e.message),
  });

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        setError(null);
        m.mutate();
      }}
      className="mt-4 rounded-lg border border-border bg-card p-5"
    >
      {error && (
        <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Name" htmlFor="s-name">
          <input
            id="s-name"
            required
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!slug) setSlug(slugify(e.target.value));
            }}
            className={input}
            placeholder="HQ Office"
          />
        </Field>
        <Field label="Slug" htmlFor="s-slug">
          <input
            id="s-slug"
            required
            pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
            minLength={2}
            value={slug}
            onChange={(e) => setSlug(e.target.value.toLowerCase())}
            className={`${input} font-mono`}
            placeholder="hq-office"
          />
        </Field>
        <Field label="Address" htmlFor="s-addr">
          <input
            id="s-addr"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            className={input}
          />
        </Field>
        <div className="md:col-span-2">
          <span className="text-xs font-medium text-muted-foreground">Location on map</span>
          <div className="mt-1">
            <SiteLocationPicker
              latitude={latitude}
              longitude={longitude}
              onChange={(lat, lng) => {
                setLatitude(lat);
                setLongitude(lng);
              }}
              address={address}
              onAddressChange={setAddress}
            />
          </div>
        </div>
        <Field label="Contact email" htmlFor="s-email">
          <input
            id="s-email"
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
            className={input}
          />
        </Field>
        <Field label="Contact phone" htmlFor="s-phone">
          <input
            id="s-phone"
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
