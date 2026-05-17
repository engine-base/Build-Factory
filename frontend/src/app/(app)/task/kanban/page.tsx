"use client";

/**
 * T-V3-C-57-3 / S-027 — タスク Kanban canonical Next.js page.
 *
 * This page is the "filter & search" slice (T-V3-C-57-3) of the S-027 surface.
 * The fuller accordion + dnd surface is owned by T-V3-C-57-1 (core) and
 * T-V3-C-57-2 (dnd). When those land, they will *replace* the placeholder
 * accordion below; this file remains the canonical mount point so the URL
 * `/task/kanban` always resolves.
 *
 * Canonical path:
 *   frontend/src/app/(app)/task/kanban/page.tsx
 *
 * Mock contract:
 *   docs/mocks/2026-05-15_v3/task/S-027-task-kanban.html
 *
 * data-* attributes used by lint-mock-impl-diff.py + Vitest spec:
 *   data-screen-id="S-027"
 *   data-feature-id="F-007"
 *   data-task-ids="T-V3-C-57-3"
 *   data-entities="E-018,E-019"
 *
 * Per CLAUDE.md §5.5: 機能別アコーディオン × 4 列. Hermes 流フラット 6 列は NG.
 */

import * as React from "react";
import { Kanban } from "lucide-react";

import {
  KanbanFilterBar,
  KanbanFilterEmptyState,
  type FilterOption,
  type KanbanFilterState,
} from "@/app/(app)/task/kanban/filter";
import { useKanbanFilter } from "@/app/(app)/task/kanban/use-kanban-filter";

// Stub data — replaced by `use-kanban-board` (T-V3-C-57-1) at integration time.
const PLACEHOLDER_FEATURES: FilterOption[] = [
  { value: "F-001", label: "Supabase 基盤 + 認証", tone: "eb" },
  { value: "F-004", label: "account/workspace/members 階層", tone: "blue" },
  { value: "F-005", label: "ヒアリング → 仕様書 pipeline", tone: "amber" },
  { value: "F-008", label: "プロジェクト・フェーズ管理", tone: "emerald" },
  { value: "F-012", label: "赤線リスト + 自動停止", tone: "purple" },
];
const PLACEHOLDER_ASSIGNEES: FilterOption[] = [
  { value: "devon", label: "devon" },
  { value: "quinn", label: "quinn" },
  { value: "winston", label: "winston" },
];

export default function TaskKanbanPage() {
  const filter = useKanbanFilter();

  // Apply filter to the placeholder feature list so the empty-state slot can
  // demo AC-F2. Real data wiring is T-V3-C-57-1's job.
  const visibleFeatures = React.useMemo(
    () => applyFilter(PLACEHOLDER_FEATURES, filter.state),
    [filter.state],
  );

  return (
    <main
      data-screen-id="S-027"
      data-feature-id="F-007"
      data-task-ids="T-V3-C-57-3"
      data-entities="E-018,E-019"
      data-phase="Phase 1"
      className="flex-1 overflow-y-auto"
    >
      <header className="px-6 py-4 border-b border-slate-200 bg-white">
        <h1 className="text-lg font-bold flex items-center gap-2">
          <Kanban className="w-5 h-5 text-eb-500" aria-hidden />
          タスク Kanban
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          機能別アコーディオン × 4 列 (Todo / In Progress / Review / Done)
        </p>
      </header>

      <KanbanFilterBar
        featureOptions={PLACEHOLDER_FEATURES}
        assigneeOptions={PLACEHOLDER_ASSIGNEES}
        value={filter.state}
        onChange={filter.setState}
      />

      <section
        data-testid="kanban-board"
        className="p-4 space-y-3"
      >
        {visibleFeatures.length === 0 ? (
          <KanbanFilterEmptyState
            sectionLabel="機能"
            onReset={filter.reset}
          />
        ) : (
          visibleFeatures.map((f) => (
            <details
              key={f.value}
              open
              className="bg-white border border-slate-200 rounded-lg overflow-hidden"
            >
              <summary className="cursor-pointer px-4 py-3 border-b border-slate-200 bg-slate-50 hover:bg-slate-100 flex items-center gap-2">
                <span className="font-bold text-sm mono">{f.value}</span>
                <span className="font-semibold text-sm">{f.label}</span>
              </summary>
              <div className="p-3 text-xs text-slate-500">
                {/* Placeholder until T-V3-C-57-1 wires the 4-column accordion body. */}
                {`(T-V3-C-57-1 で AccordionBoard + Column が入る)`}
              </div>
            </details>
          ))
        )}
      </section>
    </main>
  );
}

/** Filter the placeholder feature list per the active state.
 *  Real data fetch + filter pushdown lives in T-V3-C-57-1's hook. */
function applyFilter(
  features: FilterOption[],
  state: KanbanFilterState,
): FilterOption[] {
  let out = features;
  if (state.features.length > 0) {
    out = out.filter((f) => state.features.includes(f.value));
  }
  if (state.query.trim().length > 0) {
    const q = state.query.trim().toLowerCase();
    out = out.filter(
      (f) =>
        f.value.toLowerCase().includes(q) ||
        f.label.toLowerCase().includes(q),
    );
  }
  return out;
}
