/**
 * T-V3-C-57-1 / S-027 — Single kanban column (Todo / In Progress / Review /
 * Done) within a feature-grouped AccordionBoard section.
 *
 * Drag & drop is out of scope for the core task (T-V3-C-57-1) — see
 * T-V3-C-57-2 for the DraggableCard / DropZone wiring.
 *
 * Rendering follows the v3 mock layout
 * (docs/mocks/2026-05-15_v3/task/S-027-task-kanban.html lines 84-146):
 *
 *   <div data-kanban-column="todo" class="space-y-2">
 *     <div class="text-[10px] uppercase ... font-bold">Todo (N)</div>
 *     {tasks.map(t => <KanbanCard key={t.id} task={t} />)}
 *   </div>
 *
 * Lucide icons are used exclusively (Play / GitPullRequest / Check); no emoji.
 */

"use client";

import * as React from "react";

import { Check, GitPullRequest, Play } from "lucide-react";

import type { KanbanColumn, KanbanTask } from "@/api/kanban";

// --------------------------------------------------------------------------
// Column metadata — labels mirror the v3 mock heading copy (逐語).
// --------------------------------------------------------------------------

export const COLUMN_LABELS: Record<KanbanColumn, string> = {
  todo: "Todo",
  in_progress: "In Progress",
  review: "Review",
  done: "Done",
};

const COLUMN_HEADING_CLASSES: Record<KanbanColumn, string> = {
  todo: "text-slate-500",
  in_progress: "text-amber-600",
  review: "text-blue-600",
  done: "text-emerald-600",
};

const CARD_BORDER_CLASSES: Record<KanbanColumn, string> = {
  todo: "border-slate-200 hover:border-eb-500",
  in_progress: "border-2 border-amber-300 ring-2 ring-amber-100",
  review: "border-2 border-blue-300",
  done: "border-emerald-200 opacity-80",
};

// --------------------------------------------------------------------------
// Card sub-component
// --------------------------------------------------------------------------

interface KanbanCardProps {
  task: KanbanTask;
  column: KanbanColumn;
}

function KanbanCard({ task, column }: KanbanCardProps): React.ReactElement {
  const titleClasses =
    column === "done"
      ? "text-xs font-semibold line-through text-slate-500"
      : "text-xs font-semibold";

  // Lucide icon decoration per column — never emoji.
  const cornerIcon: React.ReactNode =
    column === "done" ? (
      <Check className="w-3 h-3 text-emerald-600" aria-hidden />
    ) : column === "review" ? (
      <GitPullRequest className="w-3 h-3 text-blue-600" aria-hidden />
    ) : column === "in_progress" ? (
      <span
        className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0"
        aria-hidden
      />
    ) : null;

  return (
    <article
      data-kanban-card={task.id}
      data-task-id={task.id}
      data-task-status={column}
      className={`bg-white rounded-md p-2.5 cursor-pointer ${CARD_BORDER_CLASSES[column]}`}
    >
      <div className="flex items-center justify-between mb-1">
        <span
          data-task-code
          className="text-[10px] mono text-slate-500"
        >
          {task.id}
        </span>
        {cornerIcon}
      </div>
      <div className={titleClasses}>{task.title}</div>
      {column === "todo" && (
        <div className="flex items-center justify-between mt-2">
          {typeof task.estimate_hours === "number" && (
            <span className="text-[10px] text-slate-500">
              {task.estimate_hours}h
            </span>
          )}
          <button
            type="button"
            aria-label="Play task"
            className="text-eb-500 hover:text-eb-600 ml-auto"
            // The play button POST is wired up in T-V3-C-57-2 / Group D E2E.
            // For the core layout task we render the affordance only.
            onClick={(event) => event.preventDefault()}
          >
            <Play className="w-3 h-3" aria-hidden />
          </button>
        </div>
      )}
    </article>
  );
}

// --------------------------------------------------------------------------
// Column component
// --------------------------------------------------------------------------

export interface KanbanColumnViewProps {
  column: KanbanColumn;
  tasks: KanbanTask[];
}

/**
 * Render one Kanban column (header + cards). All Lucide; no emoji.
 *
 * Tier 1 structural contract: the wrapping element carries
 *   - data-kanban-column="<todo|in_progress|review|done>"
 *   - data-task-count="<n>"
 * so the AccordionBoard contract test can verify the 4-column layout.
 */
export function Column({
  column,
  tasks,
}: KanbanColumnViewProps): React.ReactElement {
  const headingId = `kanban-column-${column}`;
  return (
    <section
      data-kanban-column={column}
      data-task-count={tasks.length}
      aria-labelledby={headingId}
      className="space-y-2"
    >
      <h3
        id={headingId}
        className={`text-[10px] uppercase tracking-wider font-bold px-1 py-1 ${COLUMN_HEADING_CLASSES[column]}`}
      >
        {COLUMN_LABELS[column]} ({tasks.length})
      </h3>
      {tasks.length === 0 ? (
        <p className="text-[11px] text-slate-400 px-1">—</p>
      ) : (
        tasks.map((task) => (
          <KanbanCard key={task.id} task={task} column={column} />
        ))
      )}
    </section>
  );
}
