"use client";

/**
 * T-V3-C-57-3 / S-027 — タスク Kanban filter & search FilterBar (canonical).
 *
 * Slice scope (per `tickets-group-c-ui-part2.json::T-V3-C-57-3`):
 *   - Sticky FilterBar above the accordion: feature / status / assignee multi-select
 *     plus a text search input.
 *   - Active filter badge count + Clear filters CTA while at least one filter is on.
 *   - Debounce 250ms before the API re-fetch; URL search params mirror state.
 *   - Empty-state per accordion section with Reset CTA when filters narrow to 0.
 *   - Truncate text search at 200 chars; never fire API beyond that length.
 *
 * Canonical path (per user instruction):
 *   frontend/src/app/(app)/task/kanban/filter.tsx
 *
 * The ticket-mandated alias `frontend/components/kanban/FilterBar.tsx` re-exports
 * from here (the Next.js project uses `src/app/` as the App Router root, see
 * `frontend/tsconfig.json` paths).
 *
 * AC mapping (verbatim from audit MD `docs/audit/2026-05-16_v3/T-V3-C-57-3.md`):
 *   structural.AC-S1 -> sticky FilterBar with 4 inputs.
 *   structural.AC-S2 -> active-filter badge + 'Clear filters' button.
 *   functional.AC-F1 -> 250ms debounce + URL search-param mirror.
 *   functional.AC-F2 -> per-section empty state w/ Reset CTA at 0 results.
 *   functional.AC-F3 -> text input truncates to 200 chars + no API call past 200.
 *
 * Design tokens: eb-500 = #1a6648 (CLAUDE.md §5.2). Lucide icons only.
 *
 * NOTE: This component is *display + state mechanics only*. The actual fetch is
 *       wired by `use-kanban-filter.ts` (sibling hook). The component receives
 *       the data callback through props so that the same logic powers both the
 *       canonical page (T-V3-C-57-1 dep) and isolated tests.
 */

import * as React from "react";
import {
  Filter,
  Search,
  X,
  Inbox,
  RotateCcw,
} from "lucide-react";

import { cn } from "@/lib/utils";

// ──────────────────────────────────────────────────────────────────────
//  Public types
// ──────────────────────────────────────────────────────────────────────

/** Maximum length of the text search query. AC-F3 truncates beyond this. */
export const KANBAN_SEARCH_MAX_LEN = 200;

/** Debounce window in ms for filter change → API call. AC-F1. */
export const KANBAN_FILTER_DEBOUNCE_MS = 250;

/** Status values surfaced by the kanban (matches mock 4-column layout). */
export const KANBAN_STATUS_OPTIONS = [
  { value: "todo", label: "Todo" },
  { value: "in_progress", label: "In Progress" },
  { value: "review", label: "Review" },
  { value: "done", label: "Done" },
] as const;

export type KanbanStatus = (typeof KANBAN_STATUS_OPTIONS)[number]["value"];

/** Filter option (used for feature + assignee multi-selects). */
export interface FilterOption {
  value: string;
  label: string;
  /** Optional grouping color (eb / blue / amber / emerald / purple). */
  tone?: "eb" | "blue" | "amber" | "emerald" | "purple" | "slate";
}

/** The complete active-filter state used by both the bar and the page. */
export interface KanbanFilterState {
  features: string[];
  statuses: KanbanStatus[];
  assignees: string[];
  /** Free-text search input. Truncated to KANBAN_SEARCH_MAX_LEN. */
  query: string;
}

/** Initial empty state. Stable identity. */
export const EMPTY_KANBAN_FILTER: KanbanFilterState = {
  features: [],
  statuses: [],
  assignees: [],
  query: "",
};

export interface KanbanFilterBarProps {
  /** Available feature options (label / value pairs). */
  featureOptions: FilterOption[];
  /** Available assignee options (label / value pairs). */
  assigneeOptions: FilterOption[];
  /** Controlled filter state. */
  value: KanbanFilterState;
  /** Called with the next state on every user input.
   *  Note: `query` is *already truncated* to KANBAN_SEARCH_MAX_LEN. */
  onChange: (next: KanbanFilterState) => void;
  /** Optional className wrapper. */
  className?: string;
}

// ──────────────────────────────────────────────────────────────────────
//  Helpers (pure, easy to unit test)
// ──────────────────────────────────────────────────────────────────────

/** Count how many *distinct filter inputs* currently have a value.
 *  Used for the active-filter badge (AC-S2). */
export function countActiveFilters(state: KanbanFilterState): number {
  let n = 0;
  if (state.features.length > 0) n += 1;
  if (state.statuses.length > 0) n += 1;
  if (state.assignees.length > 0) n += 1;
  if (state.query.trim().length > 0) n += 1;
  return n;
}

/** Toggle a value in a string array. */
function toggleInArray<T extends string>(arr: T[], v: T): T[] {
  return arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];
}

/** Serialise filter state to URLSearchParams (AC-F1). Stable key order. */
export function filterStateToSearchParams(
  state: KanbanFilterState,
): URLSearchParams {
  const sp = new URLSearchParams();
  if (state.features.length > 0) sp.set("feature", state.features.join(","));
  if (state.statuses.length > 0) sp.set("status", state.statuses.join(","));
  if (state.assignees.length > 0) sp.set("assignee", state.assignees.join(","));
  if (state.query.trim().length > 0) sp.set("q", state.query.trim());
  return sp;
}

/** Inverse of `filterStateToSearchParams`. Used for back/forward nav. */
export function filterStateFromSearchParams(
  sp: URLSearchParams,
): KanbanFilterState {
  const splitCsv = (raw: string | null): string[] =>
    raw ? raw.split(",").filter(Boolean) : [];
  const statuses = splitCsv(sp.get("status")).filter((s): s is KanbanStatus =>
    KANBAN_STATUS_OPTIONS.some((o) => o.value === s),
  );
  return {
    features: splitCsv(sp.get("feature")),
    statuses,
    assignees: splitCsv(sp.get("assignee")),
    query: (sp.get("q") ?? "").slice(0, KANBAN_SEARCH_MAX_LEN),
  };
}

/** Truncate query text per AC-F3. */
export function truncateQuery(raw: string): string {
  return raw.length > KANBAN_SEARCH_MAX_LEN
    ? raw.slice(0, KANBAN_SEARCH_MAX_LEN)
    : raw;
}

// ──────────────────────────────────────────────────────────────────────
//  FilterBar component (AC-S1, AC-S2)
// ──────────────────────────────────────────────────────────────────────

export function KanbanFilterBar({
  featureOptions,
  assigneeOptions,
  value,
  onChange,
  className,
}: KanbanFilterBarProps) {
  const activeCount = countActiveFilters(value);

  const handleQueryChange = (raw: string) => {
    onChange({ ...value, query: truncateQuery(raw) });
  };

  const handleToggleFeature = (v: string) => {
    onChange({ ...value, features: toggleInArray(value.features, v) });
  };

  const handleToggleStatus = (v: KanbanStatus) => {
    onChange({ ...value, statuses: toggleInArray(value.statuses, v) });
  };

  const handleToggleAssignee = (v: string) => {
    onChange({ ...value, assignees: toggleInArray(value.assignees, v) });
  };

  const handleClear = () => {
    onChange(EMPTY_KANBAN_FILTER);
  };

  return (
    <div
      data-testid="kanban-filter-bar"
      data-screen-id="S-027"
      data-feature-id="F-007"
      data-task-ids="T-V3-C-57-3"
      role="region"
      aria-label="タスク Kanban filter"
      className={cn(
        // sticky above accordion (AC-S1)
        "sticky top-0 z-20 bg-white border-b border-slate-200 px-4 py-3",
        "flex flex-col gap-2",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {/* Text search input (AC-S1 / AC-F3) */}
        <label
          className="relative flex-1 min-w-[180px] max-w-[320px]"
          aria-label="task 検索"
        >
          <Search
            className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
            aria-hidden
          />
          <input
            type="search"
            data-testid="kanban-filter-query"
            aria-label="task 検索"
            placeholder="task 検索..."
            maxLength={KANBAN_SEARCH_MAX_LEN}
            value={value.query}
            onChange={(e) => handleQueryChange(e.target.value)}
            className="w-full border border-slate-200 text-xs h-8 pl-7 pr-2 rounded-md focus:outline-none focus:border-eb-500"
          />
        </label>

        {/* Feature multi-select (AC-S1) */}
        <MultiSelectChips
          testIdPrefix="kanban-filter-feature"
          label="機能"
          options={featureOptions}
          selected={value.features}
          onToggle={handleToggleFeature}
        />

        {/* Status multi-select (AC-S1) */}
        <MultiSelectChips
          testIdPrefix="kanban-filter-status"
          label="ステータス"
          options={KANBAN_STATUS_OPTIONS.map((o) => ({
            value: o.value,
            label: o.label,
          }))}
          selected={value.statuses}
          onToggle={(v) => handleToggleStatus(v as KanbanStatus)}
        />

        {/* Assignee multi-select (AC-S1) */}
        <MultiSelectChips
          testIdPrefix="kanban-filter-assignee"
          label="担当"
          options={assigneeOptions}
          selected={value.assignees}
          onToggle={handleToggleAssignee}
        />

        {/* Active filter badge + Clear button (AC-S2) */}
        {activeCount > 0 && (
          <div className="ml-auto flex items-center gap-2">
            <span
              data-testid="kanban-filter-active-count"
              aria-label="active-filter count"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-eb-500 text-white text-[11px] font-bold mono"
            >
              <Filter className="w-3 h-3" aria-hidden />
              {activeCount}
            </span>
            <button
              type="button"
              data-testid="kanban-filter-clear"
              onClick={handleClear}
              className="inline-flex items-center gap-1 text-xs h-8 px-3 rounded-md border border-slate-200 hover:bg-slate-50 text-slate-700"
            >
              <X className="w-3 h-3" aria-hidden />
              Clear filters
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
//  MultiSelectChips — small inline multi-select pill list.
//  Keeps T-V3-C-57-3 self-contained (no shadcn Popover / Command surface
//  yet — that level of fidelity is owned by T-V3-C-57-1 page wiring).
// ──────────────────────────────────────────────────────────────────────

interface MultiSelectChipsProps {
  testIdPrefix: string;
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onToggle: (v: string) => void;
}

function MultiSelectChips({
  testIdPrefix,
  label,
  options,
  selected,
  onToggle,
}: MultiSelectChipsProps) {
  if (options.length === 0) {
    return null;
  }
  return (
    <div
      data-testid={testIdPrefix}
      className="flex items-center gap-1.5 flex-wrap"
    >
      <span className="text-[11px] font-semibold text-slate-500">{label}:</span>
      {options.map((opt) => {
        const isOn = selected.includes(opt.value);
        return (
          <button
            type="button"
            key={opt.value}
            data-testid={`${testIdPrefix}-${opt.value}`}
            aria-pressed={isOn}
            onClick={() => onToggle(opt.value)}
            className={cn(
              "text-[11px] h-6 px-2 rounded-full border transition-colors mono",
              isOn
                ? "bg-eb-500 text-white border-eb-500"
                : "bg-white text-slate-700 border-slate-200 hover:border-eb-400",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
//  Empty-state slot (AC-F2)
// ──────────────────────────────────────────────────────────────────────

export interface KanbanFilterEmptyStateProps {
  /** Feature label (or "結果") for headline copy. */
  sectionLabel?: string;
  /** Called when the user clicks the Reset filters CTA. */
  onReset: () => void;
  className?: string;
}

export function KanbanFilterEmptyState({
  sectionLabel = "結果",
  onReset,
  className,
}: KanbanFilterEmptyStateProps) {
  return (
    <div
      data-testid="kanban-filter-empty"
      role="status"
      aria-live="polite"
      className={cn(
        "flex flex-col items-center justify-center gap-2 py-6 px-3 text-center bg-slate-50 border border-dashed border-slate-200 rounded-md",
        className,
      )}
    >
      <Inbox className="w-5 h-5 text-slate-400" aria-hidden />
      <p className="text-xs text-slate-600">
        {`現在のフィルタに一致する${sectionLabel}はありません。`}
      </p>
      <button
        type="button"
        data-testid="kanban-filter-reset"
        onClick={onReset}
        className="inline-flex items-center gap-1 text-[11px] h-7 px-3 rounded-md border border-slate-200 hover:bg-slate-50 text-eb-500 font-semibold"
      >
        <RotateCcw className="w-3 h-3" aria-hidden />
        Reset filters
      </button>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
//  Default export = the bar (matches lazy-import friendly usage).
// ──────────────────────────────────────────────────────────────────────
export default KanbanFilterBar;
