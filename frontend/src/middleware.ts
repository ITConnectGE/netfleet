import { NextResponse, type NextRequest } from "next/server";

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

  // Probe setup status — Caddy or Next rewrites /api/v1 to the backend
  try {
    const origin = req.nextUrl.origin;
    const r = await fetch(`${origin}/api/v1/setup/status`, { cache: "no-store" });
    if (r.ok) {
      const { setup_complete } = (await r.json()) as { setup_complete: boolean };
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
