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
      (request) => {
        const token = authStorage.getAccessToken();
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`);
        }
      },
    ],
    afterResponse: [
      async (request, _options, response) => {
        if (response.status !== 401 || request.url.includes("/auth/")) {
          return response;
        }
        // Try refresh exactly once
        const refreshed = await tryRefresh();
        if (!refreshed) {
          authStorage.clear();
          return response;
        }
        request.headers.set("Authorization", `Bearer ${refreshed}`);
        return ky(request);
      },
    ],
  },
});

let refreshInFlight: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const json = await ky
        .post(`${API_BASE}/auth/refresh`, {
          json: {},
          credentials: "include",
          retry: { limit: 0 },
        })
        .json<{ access_token: string; expires_at: string }>();
      authStorage.setAccessToken(json.access_token, json.expires_at);
      return json.access_token;
    } catch {
      return null;
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
