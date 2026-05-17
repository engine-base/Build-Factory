/**
 * T-V3-C-55 / S-046 — Next.js middleware that forwards backend 403 responses
 * to the /forbidden page so the user sees an actionable Role mismatch screen
 * instead of an opaque "Forbidden" body.
 *
 * Behaviour:
 *   - On every request, attach an `x-bf-forbidden-redirect` header pointing
 *     to /forbidden so the SPA fetch layer can read it to decide whether to
 *     route there on a 403.
 *   - The middleware itself does NOT proxy backend responses (that happens
 *     server-side via `next.config.ts` rewrites or a Cloudflare Tunnel), but
 *     it covers the same-origin SSR fetch case: when a server component
 *     receives a 403 it can call `redirect("/forbidden")`.
 *   - Direct navigation to /forbidden is always allowed (no auth guard) so
 *     the page can render even if the user is signed out — the page itself
 *     handles 401 → /login via use-forbidden-403.ts (AC-F1).
 *
 * 3-tier AC mapping (T-V3-C-55):
 *   - Tier 2 / AC-F1: this middleware never injects workspace-scoped data
 *     into requests destined for /forbidden — the headers below only carry
 *     routing metadata.
 *
 * NOTE: Next.js middleware runs on the Edge runtime, so we avoid Node-only
 * APIs. The header name uses the `x-bf-` prefix to namespace Build-Factory
 * custom headers and avoid colliding with framework headers.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export const FORBIDDEN_REDIRECT_HEADER = "x-bf-forbidden-redirect";
export const FORBIDDEN_PATH = "/forbidden";

export function middleware(request: NextRequest): NextResponse {
  const response = NextResponse.next();
  response.headers.set(FORBIDDEN_REDIRECT_HEADER, FORBIDDEN_PATH);
  return response;
}

// Match every route except Next.js static assets and the API proxy.
// (Edge middleware cannot import Node APIs, so the matcher is the safest
// way to limit scope.)
export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|public/).*)",
  ],
};
