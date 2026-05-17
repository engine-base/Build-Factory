/**
 * T-V3-C-57-3 / S-027 — Ticket-mandated alias for the canonical
 * `useKanbanFilter` hook.
 *
 * Re-exports `frontend/src/app/(app)/task/kanban/use-kanban-filter.ts`.
 * See `frontend/components/kanban/FilterBar.tsx` for the rationale (Next.js 15
 * App Router root lives at `frontend/src/app/`).
 */

export {
  useKanbanFilter,
  KANBAN_SEARCH_MAX_LEN,
  KANBAN_FILTER_DEBOUNCE_MS,
} from "../../src/app/(app)/task/kanban/use-kanban-filter";
export type {
  UseKanbanFilterOptions,
  UseKanbanFilterResult,
} from "../../src/app/(app)/task/kanban/use-kanban-filter";
