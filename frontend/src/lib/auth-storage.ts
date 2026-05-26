/**
 * Access token storage.
 *
 * The refresh token lives in an httpOnly cookie (server-set). The access token
 * is short-lived and held in memory, with a sessionStorage shadow so that a
 * tab reload doesn't immediately bounce the user to /login.
 */

const STORAGE_KEY = "netfleet.access_token";

type Listener = (token: string | null) => void;

class AuthStorage {
  private token: string | null = null;
  private expiresAt: number | null = null;
  private listeners = new Set<Listener>();

  constructor() {
    if (typeof window !== "undefined") {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      if (raw) {
        try {
          const parsed = JSON.parse(raw);
          if (parsed.expiresAt > Date.now()) {
            this.token = parsed.token;
            this.expiresAt = parsed.expiresAt;
          }
        } catch {
          /* ignore */
        }
      }
    }
  }

  getAccessToken(): string | null {
    if (this.expiresAt && this.expiresAt < Date.now()) {
      this.clear();
      return null;
    }
    return this.token;
  }

  setAccessToken(token: string, expiresAtIso: string): void {
    this.token = token;
    this.expiresAt = new Date(expiresAtIso).getTime();
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ token, expiresAt: this.expiresAt }),
      );
    }
    this.listeners.forEach((l) => l(token));
  }

  clear(): void {
    this.token = null;
    this.expiresAt = null;
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(STORAGE_KEY);
    }
    this.listeners.forEach((l) => l(null));
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export const authStorage = new AuthStorage();
