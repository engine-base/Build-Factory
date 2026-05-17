"use client";

/**
 * T-V3-C-54 / S-045 — 500 Server Error (server_error_500) regular route page.
 *
 * Reachable at `/server-error-500` (route group `(system)` is silent in URL).
 * Used by:
 *   - the mock viewer (S-023) cross-screen link in docs/mocks/.../index.html
 *   - manual QA (visit URL directly to verify mock parity)
 *
 * The canonical body is shared with the React error boundaries
 * (`global-error.tsx` + `error.tsx`) via {@link ServerError500Content}.
 *
 * Mock-impl source of truth:
 *   docs/mocks/2026-05-15_v3/system/S-045-server-error-500.html
 * Spec:
 *   docs/functional-breakdown/2026-05-16_v3/screens.json#S-045
 */

import ServerError500Content from "@/components/system/ServerError500Content";

export default function ServerError500Page() {
  return <ServerError500Content />;
}
