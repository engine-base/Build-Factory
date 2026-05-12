"use client";

/**
 * T-007-03: task_dag_view (existing DependencyGraph.tsx REUSE wrapper).
 *
 * 既存 `frontend/src/components/dag/DependencyGraph.tsx` (T-009-02 で実装済の
 * 汎用 DAG component) は **完全無改変** (REUSE). 本 component は task 専用の
 * thin wrapper として:
 *   1. backend API から task / task_dependencies を取得 (caller 責任、props 経由)
 *   2. DependencyGraph 用 Node/Edge 形式に変換
 *   3. DependencyGraph を render
 *
 * AC マッピング (T-007-03 REUSE):
 *   AC-1 UBIQUITOUS    : <TaskDagView tasks={...} edges={...} /> 公開.
 *                        既存 DependencyGraph を REUSE (無改変).
 *   AC-2 EVENT-DRIVEN  : props 変化時 useMemo で変換再計算 / onNodeClick callback
 *                        を DependencyGraph に pass-through.
 *   AC-3 STATE-DRIVEN  : controlled component (内部 state なし) /
 *                        eb-* palette + Lucide via DependencyGraph 継承.
 *   AC-4 UNWANTED      : null / non-array tasks で fallback render (no crash).
 *                        eb-* 以外の hex literal なし.
 */

import * as React from "react";
import { Workflow } from "lucide-react";

import {
  DependencyGraph,
  type TaskStatus,
  type TaskNodeData,
  type TaskEdge,
} from "@/components/dag/DependencyGraph";
import { cn } from "@/lib/utils";

/** Task shape from backend (bf_tasks). */
export interface DagTask {
  id: number;
  title: string;
  status: string;
  assignee_name?: string | null;
  /** Parent task id (for hierarchy). null = top-level. */
  parent_task_id?: number | null;
}

/** Dependency edge (task_dependencies). */
export interface DagDependency {
  source: number;
  target: number;
  /** Hard (blocking) vs soft (informational). */
  edge_type?: "hard" | "soft";
}

export interface TaskDagViewProps {
  tasks: DagTask[];
  dependencies?: DagDependency[];
  onTaskClick?: (task: DagTask) => void;
  className?: string;
  height?: number;
}

// ──────────────────────────────────────────────────────────────────────
// Status normalization (backend status → TaskStatus)
// ──────────────────────────────────────────────────────────────────────

const VALID_STATUSES = new Set<string>([
  "pending", "in_progress", "completed",
  "blocked_question", "blocked_dependency", "failed",
]);

export function normalizeStatus(raw: string | undefined | null): TaskStatus {
  if (typeof raw !== "string") return "pending";
  const s = raw.trim();
  if (VALID_STATUSES.has(s)) return s as TaskStatus;
  // fallback mapping
  if (s === "review_needed") return "in_progress";
  if (s === "cancelled") return "failed";
  return "pending";
}

// ──────────────────────────────────────────────────────────────────────
// Conversion helpers (pure functions)
// ──────────────────────────────────────────────────────────────────────

export function tasksToNodes(tasks: DagTask[]): TaskNodeData[] {
  if (!Array.isArray(tasks)) return [];
  return tasks
    .filter((t) => t && typeof t.id === "number" && t.id > 0)
    .map((t) => ({
      id: t.id,
      title: t.title || "(untitled)",
      status: normalizeStatus(t.status),
      assignee: t.assignee_name ?? null,
    }));
}

export function dependenciesToEdges(deps: DagDependency[]): TaskEdge[] {
  if (!Array.isArray(deps)) return [];
  return deps
    .filter(
      (d) =>
        d &&
        typeof d.source === "number" && d.source > 0 &&
        typeof d.target === "number" && d.target > 0 &&
        d.source !== d.target,
    )
    .map((d) => ({
      source: d.source,
      target: d.target,
      edge_type: d.edge_type === "soft" ? "soft" : "hard",
    }));
}

// ──────────────────────────────────────────────────────────────────────
// Main component
// ──────────────────────────────────────────────────────────────────────

export function TaskDagView({
  tasks,
  dependencies = [],
  onTaskClick,
  className,
  height = 600,
}: TaskDagViewProps): React.JSX.Element {
  const validTasks = React.useMemo(
    () => (Array.isArray(tasks) ? tasks : []),
    [tasks],
  );

  const nodes = React.useMemo(() => tasksToNodes(validTasks), [validTasks]);
  const edges = React.useMemo(
    () => dependenciesToEdges(dependencies),
    [dependencies],
  );

  const handleNodeClick = React.useCallback(
    (taskData: TaskNodeData) => {
      if (!onTaskClick) return;
      const original = validTasks.find((t) => t.id === taskData.id);
      if (original) onTaskClick(original);
    },
    [onTaskClick, validTasks],
  );

  // empty / null fallback
  if (nodes.length === 0) {
    return (
      <div
        className={cn(
          "flex h-full w-full items-center justify-center text-sm text-gray-500",
          className,
        )}
        style={{ height }}
        data-testid="task-dag-empty"
      >
        <Workflow className="mr-2 h-4 w-4 text-eb-500" aria-hidden />
        タスクがまだ登録されていません
      </div>
    );
  }

  return (
    <div
      className={cn("h-full w-full", className)}
      style={{ height }}
      data-testid="task-dag-view"
    >
      <DependencyGraph
        tasks={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
      />
    </div>
  );
}

// Test-only exports
export const __testing__ = {
  normalizeStatus,
  tasksToNodes,
  dependenciesToEdges,
  VALID_STATUSES,
};
