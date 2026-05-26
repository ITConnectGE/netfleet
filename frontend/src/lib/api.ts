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
