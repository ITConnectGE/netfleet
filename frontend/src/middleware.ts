import { NextResponse, type NextRequest } from "next/server";

// Server-side only (no NEXT_PUBLIC_ prefix): the api service on the compose
// network, same default as the /api rewrite in next.config.mjs.
const INTERNAL_API_URL = (
  process.env.NETFLEET_INTERNAL_API_URL || "http://api:8000"
).replace(/\/+$/, "");

/**
 * Cheap, edge-side route protection.
 * - /dashboard/** requires a setup-complete system; auth is enforced client-side
 *   via /auth/me + httpOnly refresh cookie (we can't read either from middleware)
 * - / and /login redirect to /setup when the system isn't initialized
 *
 * The deeper authentication check lives in the dashboard layout (useQuery /auth/me).
 */
export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // No-op for static assets, API routes, _next, favicon
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname === "/favicon.ico"
  ) {
    return NextResponse.next();
  }

  // Skip setup-status probe on /setup itself
  if (pathname.startsWith("/setup")) {
    return NextResponse.next();
  }

  // Probe setup status straight at the API on the internal network. Never
  // derive this from req.nextUrl.origin: that comes from the client's Host
  // header, which would let anyone point this server-side fetch at an
  // arbitrary host (SSRF).
  try {
    const r = await fetch(`${INTERNAL_API_URL}/api/v1/setup/status`, {
      cache: "no-store",
      redirect: "error",
    });
    if (r.ok) {
      const { setup_complete } = (await r.json()) as {
        setup_complete: boolean;
      };
      if (!setup_complete && pathname !== "/setup") {
        const url = req.nextUrl.clone();
        url.pathname = "/setup";
        return NextResponse.redirect(url);
      }
    }
  } catch {
    // Backend not reachable — let the page render its own loading state
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
