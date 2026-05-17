"use client";

/**
 * T-V3-C-54 / S-045 — Next.js 15 route-level error boundary.
 *
 * This boundary catches uncaught errors raised by client components inside
 * the root layout. Unlike `global-error.tsx`, it sits INSIDE the root
 * `<html>` / `<body>` and therefore inherits the page-level
 * QueryClientProvider declared in `app/providers.tsx` / `app/layout.tsx`.
 *
 * Errors that escape *this* boundary fall through to `global-error.tsx`.
 *
 * Mock-impl source of truth:
 *   docs/mocks/2026-05-15_v3/system/S-045-server-error-500.html
 */

import * as React from "react";

import ServerError500Content from "@/components/system/ServerError500Content";
import { captureException } from "@/lib/sentry";

export interface RouteErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function RouteError({ error, reset }: RouteErrorProps) {
  React.useEffect(() => {
    void captureException(error);
  }, [error]);

  return <ServerError500Content error={error} reset={reset} />;
}
