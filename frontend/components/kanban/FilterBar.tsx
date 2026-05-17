/**
 * T-V3-C-57-3 / S-027 — Ticket-mandated alias for the canonical FilterBar.
 *
 * The Build-Factory Next.js 15 project uses `frontend/src/app/` as its App
 * Router root (see `frontend/next.config.ts` + `frontend/tsconfig.json` paths
 * `@/*` → `./src/*`). The ticket spec
 * (`tickets-group-c-ui-part2.json::T-V3-C-57-3.files_changed[0]` /
 *  `work_package_boundary.editable[0]`) declares the path
 * `frontend/components/kanban/FilterBar.tsx`, so this file exists purely to
 * satisfy that spec — it re-exports the real implementation that lives at
 * `frontend/src/app/(app)/task/kanban/filter.tsx`.
 *
 * Mirrors the pattern used by T-V3-C-44 / S-033, T-V3-C-50 / S-024,
 * T-V3-C-48 / S-022, T-V3-C-56 / S-047 etc.
 */

export {
  KanbanFilterBar,
  KanbanFilterEmptyState,
  EMPTY_KANBAN_FILTER,
  KANBAN_STATUS_OPTIONS,
  KANBAN_SEARCH_MAX_LEN,
  KANBAN_FILTER_DEBOUNCE_MS,
  countActiveFilters,
  filterStateToSearchParams,
  filterStateFromSearchParams,
  truncateQuery,
  default,
} from "../../src/app/(app)/task/kanban/filter";
export type {
  FilterOption,
  KanbanFilterBarProps,
  KanbanFilterEmptyStateProps,
  KanbanFilterState,
  KanbanStatus,
} from "../../src/app/(app)/task/kanban/filter";
