"use client";

/**
 * T-V3-C-54 / S-045 — Next.js 15 root error boundary.
 *
 * `global-error.tsx` replaces the entire root layout (including <html> and
 * <body>) when an uncaught error escapes every nested boundary. This file
 * therefore owns its own QueryClientProvider — the page-level provider in
 * `app/layout.tsx` is NOT in scope here.
 *
 * Mock-impl source of truth:
 *   docs/mocks/2026-05-15_v3/system/S-045-server-error-500.html
 *
 * Sentry breadcrumb / capture:
 *   The body component (`ServerError500Content`) calls `captureException`
 *   in a useEffect so the error reaches Sentry as soon as the boundary
 *   commits. We additionally call `captureException` here for the very
 *   first commit so the breadcrumb arrives before React strict-mode
 *   double-renders the body.
 *
 * Next.js 15 docs (`node_modules/next/dist/docs/`): error files MUST be
 * client components, MUST accept `{error, reset}`, and global-error MUST
 * render <html><body>.
 */

import * as React from "react";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";

import ServerError500Content from "@/components/system/ServerError500Content";
import { captureException } from "@/lib/sentry";

export interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  // Capture once at boundary commit. Body also captures inside a useEffect
  // to cover the (rare) case where the body is re-rendered with a fresh
  // error instance after reset() (Next.js 15 boundary behaviour).
  const [queryClient] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 0 } },
      }),
  );

  React.useEffect(() => {
    void captureException(error);
  }, [error]);

  return (
    <html lang="ja">
      <body className="bg-slate-50">
        <QueryClientProvider client={queryClient}>
          <ServerError500Content error={error} reset={reset} />
        </QueryClientProvider>
      </body>
    </html>
  );
}
