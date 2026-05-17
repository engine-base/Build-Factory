/**
 * T-V3-C-57-1 / S-027 — Feature-grouped Kanban accordion board.
 *
 * Realises CLAUDE.md §5.5 ("S-027 Kanban は機能別アコーディオン構造 —
 * Hermes 流フラット 6 列は禁止") and the v3 mock layout at
 * docs/mocks/2026-05-15_v3/task/S-027-task-kanban.html.
 *
 * 3-tier AC mapping (逐語):
 *   structural.AC-S2 — One <details> per feature_id, each containing exactly
 *     4 <section data-kanban-column> columns. Asserted by
 *     scripts/lint-mock-impl-diff.py (Tier 1 structural diff) and the page
 *     spec under frontend/tests/screens/.
 *   structural.AC-S3 — `defaultExpanded` from {@link KanbanFeatureSection}
 *     drives the `open` attribute on <details>; the page never re-computes
 *     that decision after first render so users can collapse/expand freely.
 *   structural.AC-S4 — Lucide ChevronDown / ChevronRight only; no emoji.
 *
 * Drag & drop / filter are handled in T-V3-C-57-2 / T-V3-C-57-3.
 */

"use client";

import * as React from "react";

import { ChevronDown, ChevronRight, Layers } from "lucide-react";

import type { KanbanColumn } from "@/api/kanban";
import type { KanbanFeatureSection } from "@/hooks/use-kanban-board";

import { Column } from "./Column";

// --------------------------------------------------------------------------
// Constants
// --------------------------------------------------------------------------

/**
 * Column rendering order (CLAUDE.md §5.5):
 *   "Todo / In Progress / Review / Done"
 * Mock parity: docs/mocks/2026-05-15_v3/task/S-027-task-kanban.html L84-146.
 */
export const KANBAN_COLUMN_ORDER: readonly KanbanColumn[] = [
  "todo",
  "in_progress",
  "review",
  "done",
] as const;

// --------------------------------------------------------------------------
// Single-section sub-component
// --------------------------------------------------------------------------

interface AccordionSectionProps {
  section: KanbanFeatureSection;
}

function AccordionSection({
  section,
}: AccordionSectionProps): React.ReactElement {
  const [open, setOpen] = React.useState<boolean>(section.defaultExpanded);
  const todoCount = section.columns.todo.length;
  const wipCount = section.columns.in_progress.length;
  const reviewCount = section.columns.review.length;
  const doneCount = section.columns.done.length;
  const summaryId = `kanban-section-${section.feature_id}-summary`;

  return (
    <details
      open={open}
      data-kanban-section
      data-feature-id={section.feature_id}
      data-total={section.total}
      data-default-expanded={section.defaultExpanded ? "true" : "false"}
      className="bg-white border border-slate-200 rounded-lg overflow-hidden"
    >
      <summary
        id={summaryId}
        onClick={(event) => {
          // <details>/<summary> default behavior already toggles `open`;
          // we shadow the DOM state with React so consumers can read it.
          event.preventDefault();
          setOpen((current) => !current);
        }}
        className="cursor-pointer px-4 py-3 border-b border-slate-200 bg-slate-50 hover:bg-slate-100 flex items-center gap-2 list-none"
      >
        {open ? (
          <ChevronDown
            className="w-4 h-4 text-slate-500 shrink-0"
            aria-hidden
          />
        ) : (
          <ChevronRight
            className="w-4 h-4 text-slate-500 shrink-0"
            aria-hidden
          />
        )}
        <span className="font-bold text-sm flex items-center gap-2">
          <span
            className="w-6 h-6 rounded bg-eb-500 text-white text-[10px] font-bold flex items-center justify-center mono"
            aria-hidden
          >
            <Layers className="w-3.5 h-3.5" aria-hidden />
          </span>
          {section.feature_id} {section.name}
        </span>
        <span
          data-section-total
          className="text-xs text-slate-500 mono"
        >
          {section.total} task · {doneCount}/{section.total} done
        </span>
        <div className="ml-auto flex items-center gap-1.5 text-[11px]">
          <span
            data-section-todo
            className="bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full mono"
          >
            {todoCount} todo
          </span>
          <span
            data-section-wip
            className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full mono"
          >
            {wipCount} wip
          </span>
          <span
            data-section-review
            className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full mono"
          >
            {reviewCount} review
          </span>
          <span
            data-section-done
            className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full mono"
          >
            {doneCount} done
          </span>
        </div>
      </summary>

      <div
        data-kanban-columns
        className="grid grid-cols-4 gap-3 p-3 bg-slate-50"
      >
        {KANBAN_COLUMN_ORDER.map((col) => (
          <Column key={col} column={col} tasks={section.columns[col]} />
        ))}
      </div>
    </details>
  );
}

// --------------------------------------------------------------------------
// Top-level board
// --------------------------------------------------------------------------

export interface AccordionBoardProps {
  sections: KanbanFeatureSection[];
}

/**
 * Render the entire feature-grouped kanban board. Each `section` becomes one
 * <details data-kanban-section> with 4 <section data-kanban-column> columns.
 *
 * The board never renders a flat 6-column layout (CLAUDE.md §5.5 forbids the
 * Hermes layout — enforced by tests as well as by the static layout here).
 */
export function AccordionBoard({
  sections,
}: AccordionBoardProps): React.ReactElement {
  if (sections.length === 0) {
    return (
      <div
        data-kanban-empty
        className="bg-white border border-dashed border-slate-300 rounded-lg p-8 text-center text-sm text-slate-500"
      >
        まだタスクが登録されていません
      </div>
    );
  }
  return (
    <div data-kanban-board className="p-4 space-y-3">
      {sections.map((section) => (
        <AccordionSection key={section.feature_id} section={section} />
      ))}
    </div>
  );
}
