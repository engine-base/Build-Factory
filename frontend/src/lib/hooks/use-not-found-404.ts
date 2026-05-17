/**
 * T-V3-C-53 / S-044 — `useNotFound404` hook.
 *
 * S-044 is a static system page (`bf-related-apis` = "N/A (static page)") so
 * there is nothing to fetch. The hook exists to keep the Vertical Slice
 * four-file shape (`tickets-group-c-ui-part2.json#T-V3-C-53.files_changed`)
 * and to encapsulate the two interactions surfaced on the page:
 *
 *   1. Filtering the curated `NOT_FOUND_KNOWN_ROUTES` suggestion list against
 *      a search box typed by the visitor.
 *   2. Capturing the path that produced the 404 (`window.location.pathname`)
 *      so the page can echo it back to the visitor in the mock's
 *      `requested:` mono badge.
 *
 * The hook is intentionally lightweight: no TanStack Query, no fetch — it
 * boils down to two `React.useState` hooks plus a `React.useMemo` filter.
 * AC-F2 (UNAUTHENTICATED → /login) is *not* triggered here because S-044 is
 * a public system page; the redirect logic in the page component only fires
 * if a workspace-scoped path is detected (which is never the case for a
 * pure 404).
 */

"use client";

import * as React from "react";

import {
  getKnownRoutes,
  type KnownRoute,
} from "@/lib/api/not-found-404";

export interface UseNotFound404Result {
  /** Text typed into the search box (controlled). */
  readonly query: string;
  /** Setter for {@link query}. */
  readonly setQuery: (q: string) => void;
  /**
   * Filtered subset of {@link KnownRoute} matching {@link query}. When `query`
   * is empty, returns the full catalogue unchanged. Matching is
   * case-insensitive against `label` and `description` so both Japanese and
   * Latin characters surface useful hits.
   */
  readonly matches: readonly KnownRoute[];
  /**
   * Path that produced the 404 — `window.location.pathname` captured on
   * mount, or `null` while rendering on the server. The page renders this
   * inside the mono `requested:` badge to mirror the mock.
   */
  readonly requestedPath: string | null;
}

/** Hook backing the S-044 404 page. See module doc for behavioural contract. */
export function useNotFound404(): UseNotFound404Result {
  const [query, setQuery] = React.useState("");
  const [requestedPath, setRequestedPath] = React.useState<string | null>(null);

  // Capture the offending URL once on the client. Guard against SSR by
  // checking `typeof window` — Next.js renders the not-found segment on the
  // server first, and `window` is undefined there.
  React.useEffect(() => {
    if (typeof window !== "undefined") {
      setRequestedPath(window.location.pathname || "/");
    }
  }, []);

  const matches = React.useMemo<readonly KnownRoute[]>(() => {
    const trimmed = query.trim().toLowerCase();
    const all = getKnownRoutes();
    if (trimmed.length === 0) return all;
    return all.filter(
      (route) =>
        route.label.toLowerCase().includes(trimmed) ||
        route.description.toLowerCase().includes(trimmed) ||
        route.href.toLowerCase().includes(trimmed),
    );
  }, [query]);

  return { query, setQuery, matches, requestedPath };
}
