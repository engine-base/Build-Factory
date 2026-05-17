"use client";

/**
 * T-V3-C-57-3 / S-027 — useKanbanFilter hook (canonical).
 *
 * Provides controlled filter state + 250ms-debounced "committed" state used by
 * data fetchers. Mirrors the active filter state to URL search params so that
 * back/forward navigation restores the same filter view (AC-F1).
 *
 * Canonical path:
 *   frontend/src/app/(app)/task/kanban/use-kanban-filter.ts
 *
 * Ticket-mandated alias `frontend/lib/hooks/use-kanban-filter.ts` re-exports
 * from here.
 *
 * AC mapping:
 *   functional.AC-F1 -> debounce 250ms then expose `debouncedState`; pushes
 *                       URL search params to `window.history` on each commit.
 *   functional.AC-F3 -> `setQuery` truncates to KANBAN_SEARCH_MAX_LEN.
 *
 * The hook is *display-agnostic*: it only owns state mechanics. The actual
 * API call belongs to the calling page (T-V3-C-57-1) — it watches
 * `debouncedState` to know when to refetch.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  EMPTY_KANBAN_FILTER,
  KANBAN_FILTER_DEBOUNCE_MS,
  KANBAN_SEARCH_MAX_LEN,
  filterStateFromSearchParams,
  filterStateToSearchParams,
  truncateQuery,
  type KanbanFilterState,
  type KanbanStatus,
} from "@/app/(app)/task/kanban/filter";

export interface UseKanbanFilterOptions {
  /** Initial state (defaults to EMPTY_KANBAN_FILTER + hydration from URL). */
  initial?: KanbanFilterState;
  /** When false, skip `window.history.replaceState` (useful for tests). */
  syncUrl?: boolean;
  /** Debounce window in ms (defaults to KANBAN_FILTER_DEBOUNCE_MS). */
  debounceMs?: number;
}

export interface UseKanbanFilterResult {
  /** Current (un-debounced) filter state. */
  state: KanbanFilterState;
  /** Debounced filter state — only changes after `debounceMs` of inactivity. */
  debouncedState: KanbanFilterState;
  /** Replace the entire filter state. */
  setState: (next: KanbanFilterState) => void;
  /** Update a single field. */
  setQuery: (raw: string) => void;
  toggleFeature: (v: string) => void;
  toggleStatus: (v: KanbanStatus) => void;
  toggleAssignee: (v: string) => void;
  /** Reset to EMPTY_KANBAN_FILTER (AC-F2 reset CTA). */
  reset: () => void;
  /** Number of active distinct filter inputs (mirrors `countActiveFilters`). */
  activeCount: number;
}

/** Read initial state from `window.location.search` when available. */
function initialFromUrl(initial?: KanbanFilterState): KanbanFilterState {
  if (initial) return initial;
  if (typeof window === "undefined") return EMPTY_KANBAN_FILTER;
  try {
    return filterStateFromSearchParams(
      new URLSearchParams(window.location.search),
    );
  } catch {
    return EMPTY_KANBAN_FILTER;
  }
}

/** Stable shallow-equality check for filter state. */
function filterStatesEqual(
  a: KanbanFilterState,
  b: KanbanFilterState,
): boolean {
  return (
    a.query === b.query &&
    a.features.length === b.features.length &&
    a.statuses.length === b.statuses.length &&
    a.assignees.length === b.assignees.length &&
    a.features.every((v, i) => v === b.features[i]) &&
    a.statuses.every((v, i) => v === b.statuses[i]) &&
    a.assignees.every((v, i) => v === b.assignees[i])
  );
}

export function useKanbanFilter(
  options: UseKanbanFilterOptions = {},
): UseKanbanFilterResult {
  const syncUrl = options.syncUrl ?? true;
  const debounceMs = options.debounceMs ?? KANBAN_FILTER_DEBOUNCE_MS;

  const [state, setStateRaw] = useState<KanbanFilterState>(() =>
    initialFromUrl(options.initial),
  );
  const [debouncedState, setDebouncedState] = useState<KanbanFilterState>(
    () => state,
  );

  // Debounce the committed state used by data fetchers (AC-F1).
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(() => {
      setDebouncedState((prev) =>
        filterStatesEqual(prev, state) ? prev : state,
      );
      timerRef.current = null;
    }, debounceMs);
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [state, debounceMs]);

  // Mirror to URL search params on every committed change (AC-F1).
  useEffect(() => {
    if (!syncUrl || typeof window === "undefined") return;
    const sp = filterStateToSearchParams(debouncedState);
    const next = sp.toString();
    const current = window.location.search.replace(/^\?/, "");
    if (next === current) return;
    const url = next.length === 0
      ? window.location.pathname
      : `${window.location.pathname}?${next}`;
    try {
      window.history.replaceState(null, "", url);
    } catch {
      /* jsdom + SSR safety */
    }
  }, [debouncedState, syncUrl]);

  const setState = useCallback((next: KanbanFilterState) => {
    setStateRaw({
      ...next,
      query: truncateQuery(next.query),
    });
  }, []);

  const setQuery = useCallback((raw: string) => {
    setStateRaw((prev) => ({ ...prev, query: truncateQuery(raw) }));
  }, []);

  const toggleFeature = useCallback((v: string) => {
    setStateRaw((prev) => ({
      ...prev,
      features: prev.features.includes(v)
        ? prev.features.filter((x) => x !== v)
        : [...prev.features, v],
    }));
  }, []);

  const toggleStatus = useCallback((v: KanbanStatus) => {
    setStateRaw((prev) => ({
      ...prev,
      statuses: prev.statuses.includes(v)
        ? prev.statuses.filter((x) => x !== v)
        : [...prev.statuses, v],
    }));
  }, []);

  const toggleAssignee = useCallback((v: string) => {
    setStateRaw((prev) => ({
      ...prev,
      assignees: prev.assignees.includes(v)
        ? prev.assignees.filter((x) => x !== v)
        : [...prev.assignees, v],
    }));
  }, []);

  const reset = useCallback(() => {
    setStateRaw(EMPTY_KANBAN_FILTER);
  }, []);

  const activeCount = useMemo(() => {
    let n = 0;
    if (state.features.length > 0) n += 1;
    if (state.statuses.length > 0) n += 1;
    if (state.assignees.length > 0) n += 1;
    if (state.query.trim().length > 0) n += 1;
    return n;
  }, [state]);

  return {
    state,
    debouncedState,
    setState,
    setQuery,
    toggleFeature,
    toggleStatus,
    toggleAssignee,
    reset,
    activeCount,
  };
}

export { KANBAN_SEARCH_MAX_LEN, KANBAN_FILTER_DEBOUNCE_MS };
