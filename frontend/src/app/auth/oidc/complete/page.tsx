"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { authStorage } from "@/lib/auth-storage";

/**
 * OIDC redirect target.
 * Backend redirects here with `#access_token=<jwt>` after a successful login.
 * We stash the token and bounce to /dashboard.
 */
export default function OidcCompletePage() {
  const router = useRouter();

  useEffect(() => {
    const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";
    const params = new URLSearchParams(hash);
    const token = params.get("access_token");
    if (!token) {
      router.replace("/login?error=oidc");
      return;
    }
    // Backend already set the refresh cookie + this access token's expiry is in JWT exp.
    // We accept a generous window (15min) here; the next /auth/me will refresh if needed.
    const expiresAt = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    authStorage.setAccessToken(token, expiresAt);
    router.replace("/dashboard");
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-muted-foreground">Completing sign-in…</p>
    </main>
  );
}
