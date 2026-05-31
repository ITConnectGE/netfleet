import Link from "next/link";

import { LogoMark } from "@/components/logo";

export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-slate-50 via-white to-emerald-50 p-8 dark:from-slate-950 dark:via-background dark:to-slate-900">
      <div className="mx-auto max-w-2xl text-center">
        <div className="mb-6 flex justify-center">
          <LogoMark size={72} />
        </div>

        <h1 className="text-balance text-5xl font-semibold tracking-tight md:text-6xl">
          NetFleet
        </h1>
        <p className="mt-3 text-balance text-lg text-muted-foreground">
          Multi-vendor network fleet management for MSPs.
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          MikroTik today · FortiGate, Cisco &amp; more on the roadmap.
        </p>

        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/login"
            className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground transition hover:opacity-90"
          >
            Sign in
          </Link>
          <a
            href="/docs"
            className="inline-flex items-center justify-center rounded-md border border-border bg-card px-6 py-2.5 text-sm font-medium text-foreground transition hover:bg-accent"
          >
            API docs
          </a>
        </div>

        <footer className="mt-16 text-xs text-muted-foreground">
          An open-source project by{" "}
          <a
            href="https://itconnect.ge"
            target="_blank"
            rel="noreferrer"
            className="underline-offset-4 hover:underline"
          >
            ITConnect
          </a>{" "}
          · Apache-2.0
        </footer>
      </div>
    </main>
  );
}
