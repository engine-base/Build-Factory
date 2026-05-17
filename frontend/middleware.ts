/**
 * T-V3-C-56 / S-047 — Maintenance mode middleware.
 *
 * When the `MAINTENANCE_MODE` env flag is set (truthy: "1" / "true" / "on"),
 * every request that is *not* already targeting the maintenance page or its
 * required static assets is rewritten to `/maintenance` with HTTP 503
 * (Service Unavailable). This drains the workspace UI off the wire while the
 * maintenance window is active.
 *
 * Env flag precedence:
 *   1. process.env.MAINTENANCE_MODE          (Vercel / Oracle Cloud runtime)
 *   2. process.env.NEXT_PUBLIC_MAINTENANCE   (client-side override, used by
 *                                              vitest for the structural spec)
 *
 * Bypass paths (still served while maintenance is active):
 *   - /maintenance          : the maintenance page itself.
 *   - /_next/*              : the Next.js build pipeline assets.
 *   - /favicon.ico          : prevents browser favicon 503 loops.
 *   - /api/system/maintenance : the status endpoint feeding the page.
 *
 * Response semantics:
 *   - 503 Service Unavailable + Retry-After: 3600
 *   - X-Maintenance-Mode: active (operator inspection only)
 *   - Body: HTML rewrite to /maintenance via NextResponse.rewrite — the page
 *           is rendered server-side so the user sees the maintenance UI even
 *           if their client refuses redirects.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const MAINTENANCE_BYPASS_PREFIXES = [
  "/maintenance",
  "/_next/",
  "/favicon.ico",
  "/api/system/maintenance",
];

/**
 * Parse the env flag into a boolean. Exported for tests so we don't have to
 * stub the entire middleware to assert flag parsing.
 */
export function isMaintenanceModeEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  const raw =
    env.MAINTENANCE_MODE ?? env.NEXT_PUBLIC_MAINTENANCE ?? "";
  if (!raw) return false;
  const normalised = String(raw).trim().toLowerCase();
  return (
    normalised === "1" ||
    normalised === "true" ||
    normalised === "on" ||
    normalised === "yes"
  );
}

/**
 * Return true if this request should bypass the maintenance gate.
 * Exported for tests.
 */
export function shouldBypassMaintenance(pathname: string): boolean {
  return MAINTENANCE_BYPASS_PREFIXES.some(
    (prefix) =>
      pathname === prefix ||
      pathname.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`),
  );
}

export function middleware(request: NextRequest): NextResponse {
  if (!isMaintenanceModeEnabled()) {
    return NextResponse.next();
  }
  const pathname = request.nextUrl.pathname;
  if (shouldBypassMaintenance(pathname)) {
    return NextResponse.next();
  }

  // Rewrite (not redirect) so the URL bar shows the original request, but
  // emit 503 + Retry-After so monitoring infrastructure (Sentry / Better
  // Stack) correctly classifies the outage.
  const url = request.nextUrl.clone();
  url.pathname = "/maintenance";
  const resp = NextResponse.rewrite(url, { status: 503 });
  resp.headers.set("Retry-After", "3600");
  resp.headers.set("X-Maintenance-Mode", "active");
  return resp;
}

/**
 * Match every request *except* Next.js internals and static assets. The
 * runtime bypass list in `shouldBypassMaintenance` adds another safety net
 * for /favicon.ico and the maintenance status API.
 */
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
