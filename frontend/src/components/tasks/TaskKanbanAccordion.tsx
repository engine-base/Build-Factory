"use client";

/**
 * T-007-01: TaskKanban 機能別アコーディオン (CLAUDE.md §5.5 準拠).
 *
 * 既存 TaskKanban.tsx (フラット 6 列 board) は **完全無改変** (REUSE).
 * 本 component は CLAUDE.md §5.5 が要求する以下の構造を実装:
 *
 *   "S-027 Kanban は機能別アコーディオン構造 (Hermes flat 6-column = NG)"
 *   "各機能内で 4 列: Todo / In Progress / Review / Done"
 *   "進行中の機能のみデフォルト展開、完了済みは折りたたみ"
 *
 * ## 設計
 *   - parent_task_id == null の task = "機能" (アコーディオン項目)
 *   - 子 task を 4 列に振り分け (Todo / In Progress / Review / Done)
 *   - 機能のステータス (進行中/完了) で default open を判定
 *
 * ## CLAUDE.md §5 厳格遵守
 *   - eb-500 主色 (eb-500/400/200)
 *   - Lucide only (ChevronDown / Folder / 各 status icon)
 *   - shadcn/ui Accordion (利用可能なら) / fallback で details/summary
 *   - 絵文字なし
 *
 * AC マッピング (T-007-01 REFACTOR):
 *   AC-1 UBIQUITOUS    : 機能別アコーディオン + 各機能内 4 列を render.
 *                        既存 TaskKanban.tsx 無改変.
 *   AC-2 EVENT-DRIVEN  : props 変更時 useMemo で再計算 / onTaskClick callback.
 *   AC-3 STATE-DRIVEN  : 進行中の機能のみ default 展開 / 完了済みは折りたたみ.
 *   AC-4 UNWANTED      : empty tasks で fallback render / null-safe.
 */

import * as React from "react";
import {
  Clock, CheckCircle, AlertCircle, ChevronDown, Folder,
} from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Task shape (既存 TaskKanban.tsx の Task と互換).
 */
export interface AccordionTask {
  id: number;
  parent_task_id: number | null;
  title: string;
  status: string;
  level?: number;
  assignee_name?: string | null;
  skill_name?: string;
}

export interface TaskKanbanAccordionProps {
  tasks: AccordionTask[];
  onTaskClick?: (task: AccordionTask) => void;
  /** 全機能を default で展開する (test 用). false でデフォルト規則に従う. */
  defaultAllOpen?: boolean;
  className?: string;
}

// ──────────────────────────────────────────────────────────────────────
// 4 column definition (CLAUDE.md §5.5 厳守)
// ──────────────────────────────────────────────────────────────────────

const FOUR_COLUMNS: {
  id: string;
  title: string;
  matches: readonly string[];
  Icon: typeof Clock;
  borderClass: string;
}[] = [
  {
    id: "todo",
    title: "Todo",
    matches: ["pending"],
    Icon: Clock,
    borderClass: "border-eb-200",
  },
  {
    id: "in_progress",
    title: "In Progress",
    matches: ["in_progress"],
    Icon: Clock,
    borderClass: "border-eb-500",
  },
  {
    id: "review",
    title: "Review",
    matches: ["review_needed", "blocked_question"],
    Icon: AlertCircle,
    borderClass: "border-eb-400",
  },
  {
    id: "done",
    title: "Done",
    matches: ["completed"],
    Icon: CheckCircle,
    borderClass: "border-eb-200",
  },
];

const VALID_COLUMN_IDS = FOUR_COLUMNS.map((c) => c.id);

// ──────────────────────────────────────────────────────────────────────
// Helpers (pure functions, testable)
// ──────────────────────────────────────────────────────────────────────

/**
 * task status → 4 column id ("todo"/"in_progress"/"review"/"done"/"other").
 */
export function statusToColumnId(status: string): string {
  if (typeof status !== "string") return "other";
  const s = status.trim();
  for (const col of FOUR_COLUMNS) {
    if (col.matches.includes(s)) return col.id;
  }
  return "other";
}

/**
 * 機能 (parent task) が "進行中" か判定.
 * - 子 task に "in_progress" がいれば in-progress
 * - もしくは feature 自身が "in_progress"
 */
export function isFeatureInProgress(
  feature: AccordionTask,
  children: AccordionTask[],
): boolean {
  if (feature.status === "in_progress") return true;
  return children.some((c) => c.status === "in_progress");
}

/**
 * 機能が "完了済み" か判定 (全 child が completed).
 */
export function isFeatureCompleted(
  feature: AccordionTask,
  children: AccordionTask[],
): boolean {
  if (children.length === 0) return feature.status === "completed";
  return children.every((c) => c.status === "completed");
}

// ──────────────────────────────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────────────────────────────

export function TaskKanbanAccordion({
  tasks,
  onTaskClick,
  defaultAllOpen = false,
  className,
}: TaskKanbanAccordionProps): React.JSX.Element {
  const validTasks = React.useMemo(
    () => (Array.isArray(tasks) ? tasks : []),
    [tasks],
  );

  // parent (機能) と child を分離
  const features = React.useMemo(
    () => validTasks.filter((t) => t.parent_task_id == null),
    [validTasks],
  );

  const childrenByFeature = React.useMemo(() => {
    const map = new Map<number, AccordionTask[]>();
    for (const t of validTasks) {
      if (t.parent_task_id == null) continue;
      const arr = map.get(t.parent_task_id) ?? [];
      arr.push(t);
      map.set(t.parent_task_id, arr);
    }
    return map;
  }, [validTasks]);

  if (features.length === 0) {
    return (
      <div
        className={cn(
          "flex items-center justify-center p-6 text-sm text-gray-500",
          className,
        )}
        data-testid="kanban-accordion-empty"
      >
        <Folder className="mr-2 h-4 w-4" aria-hidden />
        機能 (parent task) がまだ登録されていません
      </div>
    );
  }

  return (
    <div
      className={cn("space-y-2", className)}
      data-testid="kanban-accordion"
    >
      {features.map((feature) => {
        const children = childrenByFeature.get(feature.id) ?? [];
        const inProgress = isFeatureInProgress(feature, children);
        const completed = isFeatureCompleted(feature, children);
        const defaultOpen = defaultAllOpen || (inProgress && !completed);

        return (
          <FeatureAccordionItem
            key={feature.id}
            feature={feature}
            children_={children}
            defaultOpen={defaultOpen}
            isCompleted={completed}
            onTaskClick={onTaskClick}
          />
        );
      })}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Feature accordion item (details/summary fallback, shadcn-aware)
// ──────────────────────────────────────────────────────────────────────

function FeatureAccordionItem({
  feature,
  children_,
  defaultOpen,
  isCompleted,
  onTaskClick,
}: {
  feature: AccordionTask;
  children_: AccordionTask[];
  defaultOpen: boolean;
  isCompleted: boolean;
  onTaskClick?: (task: AccordionTask) => void;
}): React.JSX.Element {
  // 4 列に振り分け
  const byColumn = React.useMemo(() => {
    const map: Record<string, AccordionTask[]> = {
      todo: [], in_progress: [], review: [], done: [], other: [],
    };
    for (const c of children_) {
      const col = statusToColumnId(c.status);
      (map[col] ?? map.other).push(c);
    }
    return map;
  }, [children_]);

  return (
    <details
      open={defaultOpen}
      className={cn(
        "rounded-lg border-2 bg-white",
        isCompleted ? "border-eb-200" : "border-eb-500",
      )}
      data-testid={`kanban-feature-${feature.id}`}
      data-feature-completed={isCompleted ? "true" : "false"}
      data-default-open={defaultOpen ? "true" : "false"}
    >
      <summary
        className={cn(
          "flex cursor-pointer items-center gap-2 px-4 py-2",
          isCompleted ? "bg-white" : "bg-eb-50",
        )}
      >
        <ChevronDown
          className="h-4 w-4 transition-transform"
          aria-hidden
        />
        <Folder
          className={cn(
            "h-4 w-4",
            isCompleted ? "text-eb-200" : "text-eb-500",
          )}
          aria-hidden
        />
        <span className="font-medium">{feature.title}</span>
        <span className="ml-auto text-xs text-gray-500">
          {children_.length} 件
        </span>
      </summary>

      {/* 4 columns (CLAUDE.md §5.5 厳守) */}
      <div
        className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-4"
        data-testid={`kanban-feature-${feature.id}-columns`}
      >
        {FOUR_COLUMNS.map((col) => (
          <div
            key={col.id}
            className={cn(
              "rounded-md border-2 bg-gray-50 p-2",
              col.borderClass,
            )}
            data-testid={`kanban-column-${col.id}`}
          >
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold">
              <col.Icon className="h-3.5 w-3.5" aria-hidden />
              <span>{col.title}</span>
              <span className="ml-auto text-gray-500">
                {(byColumn[col.id] ?? []).length}
              </span>
            </div>
            <div className="space-y-1.5">
              {(byColumn[col.id] ?? []).map((task) => (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => onTaskClick?.(task)}
                  className="block w-full rounded border border-eb-200 bg-white px-2 py-1.5 text-left text-xs hover:border-eb-400"
                  data-testid={`kanban-task-${task.id}`}
                >
                  {task.title}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Test-only exports
// ──────────────────────────────────────────────────────────────────────

export const __testing__ = {
  FOUR_COLUMNS,
  VALID_COLUMN_IDS,
  statusToColumnId,
  isFeatureInProgress,
  isFeatureCompleted,
};
