import ky, { HTTPError, type KyInstance } from "ky";

import { authStorage } from "@/lib/auth-storage";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window === "undefined" ? "http://api:8000/api/v1" : "/api/v1");

/**
 * Single shared API client.
 * - Sends Authorization: Bearer <access_token> when present
 * - On 401 with code-aware retry, attempts /auth/refresh once and re-tries
 */
export const api: KyInstance = ky.create({
  prefixUrl: API_BASE,
  credentials: "include", // include httpOnly refresh cookie
  timeout: 30_000,
  retry: { limit: 0 },
  hooks: {
    beforeRequest: [
      async (request) => {
        // Proactive refresh: if the access token is within 60 s of
        // expiry — or already gone but a refresh cookie may still be
        // valid — try to mint a fresh one before the request goes out.
        // Avoids the "tab idle for 16 min → first click 401s" round
        // trip and keeps the layout's /auth/me poll silent.
        if (
          !request.url.includes("/auth/refresh") &&
          !request.url.endsWith("/auth/login") &&
          authStorage.isExpiringSoon(60_000)
        ) {
          await tryRefresh();
        }
        const token = authStorage.getAccessToken();
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`);
        }
      },
    ],
    afterResponse: [
      async (request, _options, response) => {
        // Only bootstrap auth endpoints are excluded — `/auth/refresh`
        // because retrying it after a 401 would loop, `/auth/login` /
        // `/auth/totp/verify` / `/auth/otp/verify` because their 401
        // means "bad credentials", not "stale access token". For
        // everything else (including `/auth/me`, which is what the
        // layout polls every few seconds) a 401 should opportunistically
        // try the refresh — that's the difference between "session
        // continues" and "user gets bounced to /login after 15 min".
        const u = request.url;
        const skip =
          response.status !== 401 ||
          u.includes("/auth/refresh") ||
          u.endsWith("/auth/login") ||
          u.endsWith("/auth/totp/verify") ||
          u.endsWith("/auth/otp/verify") ||
          u.endsWith("/auth/otp/send");
        if (skip) return response;
        const refreshed = await tryRefresh();
        if (!refreshed) {
          // Only forget the session when the server actually rejected the
          // refresh. A timeout or a 502 while the API restarts says nothing
          // about the session; wiping it there bounced people to /login.
          if (lastRefreshRejected) authStorage.clear();
          return response;
        }
        request.headers.set("Authorization", `Bearer ${refreshed}`);
        return ky(request);
      },
    ],
  },
});

let refreshInFlight: Promise<string | null> | null = null;
/** True when the last refresh failed because the server said no (401),
 *  as opposed to a network error or 5xx. */
let lastRefreshRejected = false;

async function doRefresh(): Promise<string | null> {
  try {
    const json = await ky
      .post(`${API_BASE}/auth/refresh`, {
        json: {},
        credentials: "include",
        retry: { limit: 0 },
      })
      .json<{ access_token: string; expires_at: string }>();
    lastRefreshRejected = false;
    authStorage.setAccessToken(json.access_token, json.expires_at);
    return json.access_token;
  } catch (e) {
    lastRefreshRejected = e instanceof HTTPError && e.response.status === 401;
    return null;
  }
}

async function tryRefresh(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      // Every tab holds its own access token but they share one refresh
      // cookie, and each refresh rotates it. Serialise refreshes across
      // tabs so the second tab presents the cookie the first one just
      // received instead of the one it just retired.
      if (typeof navigator !== "undefined" && navigator.locks) {
        return await navigator.locks.request("netfleet-auth-refresh", doRefresh);
      }
      return await doRefresh();
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export function isHttpError(e: unknown): e is HTTPError {
  return e instanceof HTTPError;
}

/** Authenticated file download. <a href download> doesn't carry the
 *  bearer token, so any /api/v1/* endpoint guarded by auth 401s before
 *  the browser save dialog is even reached. Use this helper for every
 *  downloadable file the API exposes — backups, onboarding scripts,
 *  system bundles, CSV reports. */
export async function downloadAuthed(
  url: string,
  fallbackFilename: string,
): Promise<void> {
  const token = authStorage.getAccessToken();
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`download failed: HTTP ${res.status}`);
  }
  const disp = res.headers.get("Content-Disposition") ?? "";
  const match = disp.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? fallbackFilename;
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

export async function readErrorMessage(e: unknown): Promise<string> {
  if (isHttpError(e)) {
    try {
      const body = (await e.response.clone().json()) as { detail?: string };
      if (body.detail) return body.detail;
    } catch {
      /* fallthrough */
    }
    return `${e.response.status} ${e.response.statusText}`;
  }
  return (e as Error)?.message ?? "Unknown error";
}
