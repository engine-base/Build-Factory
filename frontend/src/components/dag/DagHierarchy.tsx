"use client";

/**
 * T-009-04: DAG 仮想化 + 階層折りたたみ helpers.
 *
 * 既存 DependencyGraph.tsx (T-009-02) は **完全無改変** (REUSE).
 * 大規模 DAG (1000+ ノード) の rendering を最適化するための:
 *   1. 階層折りたたみ (collapse parents) → 表示ノード数削減
 *   2. depth filtering → 表示深度制御
 *   3. visible nodes filtering → React Flow に渡す前段
 *
 * を提供する純関数 + 軽量 wrapper component.
 *
 * @xyflow/react built-in の仮想化 (元々 viewport 外は不可視) と合わせて、
 * 数千ノード規模でも 60fps を狙う.
 *
 * AC マッピング (T-009-04 NEW):
 *   AC-1 UBIQUITOUS    : 階層折りたたみ + depth filter helpers を公開.
 *                        既存 DependencyGraph 無改変.
 *   AC-2 EVENT-DRIVEN  : toggleCollapse / setMaxDepth の callback / useMemo.
 *   AC-3 STATE-DRIVEN  : 折りたたみ state は controlled (caller 持ち) /
 *                        eb-* palette / Lucide icons.
 *   AC-4 UNWANTED      : invalid maxDepth (負の数 / NaN) で 0 fallback /
 *                        循環参照を含むエッジでも crash しない.
 */

import * as React from "react";
import { ChevronRight, ChevronDown, Layers } from "lucide-react";

import { cn } from "@/lib/utils";

// ──────────────────────────────────────────────────────────────────────
// Types (既存 DependencyGraph.tsx の TaskNodeData / TaskEdge 互換)
// ──────────────────────────────────────────────────────────────────────

export interface HierarchyTask {
  id: number;
  title: string;
  status: string;
  parent_id?: number | null;
  level?: number;
}

export interface HierarchyEdge {
  source: number;
  target: number;
}

// ──────────────────────────────────────────────────────────────────────
// Pure helpers (testable, no React)
// ──────────────────────────────────────────────────────────────────────

const MAX_REASONABLE_DEPTH = 50;

/**
 * 各 node の depth を計算 (root = 0).
 * 循環参照あり → depth が MAX_REASONABLE_DEPTH を超えたら止める (crash 防止).
 */
export function computeDepths(
  tasks: HierarchyTask[],
  edges: HierarchyEdge[],
): Map<number, number> {
  const result = new Map<number, number>();
  if (!Array.isArray(tasks)) return result;

  const parents = new Map<number, number[]>();
  for (const e of edges ?? []) {
    if (!e || typeof e.target !== "number" || typeof e.source !== "number") {
      continue;
    }
    const arr = parents.get(e.target) ?? [];
    arr.push(e.source);
    parents.set(e.target, arr);
  }

  // depth-first with memoization + cycle guard
  function dfs(id: number, visiting: Set<number>): number {
    if (result.has(id)) return result.get(id)!;
    if (visiting.has(id)) {
      // cycle detected — return 0 (root-like)
      return 0;
    }
    visiting.add(id);
    const parentIds = parents.get(id) ?? [];
    if (parentIds.length === 0) {
      result.set(id, 0);
      visiting.delete(id);
      return 0;
    }
    let maxParentDepth = -1;
    for (const pid of parentIds) {
      if (visiting.has(pid)) continue;  // skip cycle
      maxParentDepth = Math.max(maxParentDepth, dfs(pid, visiting));
      if (maxParentDepth >= MAX_REASONABLE_DEPTH) break;
    }
    const depth = Math.min(maxParentDepth + 1, MAX_REASONABLE_DEPTH);
    result.set(id, depth);
    visiting.delete(id);
    return depth;
  }

  for (const t of tasks) {
    if (!t || typeof t.id !== "number") continue;
    dfs(t.id, new Set());
  }
  return result;
}

/**
 * 折りたたみ状態を考慮して visible task id 集合を返す.
 *
 * @param tasks       全 task
 * @param edges       全 edge
 * @param collapsedIds 折りたたみ済 parent id 集合
 * @param maxDepth    -1 で無制限, それ以上 = 表示する最大 depth
 */
export function filterVisibleTasks(
  tasks: HierarchyTask[],
  edges: HierarchyEdge[],
  collapsedIds: Set<number>,
  maxDepth: number = -1,
): Set<number> {
  const out = new Set<number>();
  if (!Array.isArray(tasks)) return out;

  const depths = computeDepths(tasks, edges);

  // depth cap validation
  const effectiveMax =
    typeof maxDepth === "number" && Number.isFinite(maxDepth) && maxDepth >= 0
      ? Math.floor(maxDepth)
      : -1;

  // child mapping (parent → children)
  const children = new Map<number, number[]>();
  for (const e of edges ?? []) {
    if (!e || typeof e.source !== "number" || typeof e.target !== "number") {
      continue;
    }
    const arr = children.get(e.source) ?? [];
    arr.push(e.target);
    children.set(e.source, arr);
  }

  // 折りたたみ済 parent の descendant を再帰的に除外
  const hidden = new Set<number>();
  const stack: number[] = Array.from(collapsedIds ?? []);
  const seen = new Set<number>();
  while (stack.length > 0) {
    const id = stack.pop()!;
    if (seen.has(id)) continue;
    seen.add(id);
    const kids = children.get(id) ?? [];
    for (const k of kids) {
      hidden.add(k);
      stack.push(k);
    }
  }

  for (const t of tasks) {
    if (!t || typeof t.id !== "number") continue;
    if (hidden.has(t.id)) continue;
    const d = depths.get(t.id) ?? 0;
    if (effectiveMax >= 0 && d > effectiveMax) continue;
    out.add(t.id);
  }
  return out;
}

// ──────────────────────────────────────────────────────────────────────
// React component (controls + summary)
// ──────────────────────────────────────────────────────────────────────

export interface DagHierarchyControlsProps {
  tasks: HierarchyTask[];
  edges?: HierarchyEdge[];
  collapsedIds: Set<number>;
  onToggleCollapse?: (id: number) => void;
  maxDepth?: number;
  onMaxDepthChange?: (depth: number) => void;
  className?: string;
}

/**
 * 折りたたみコントロール + summary 表示 component.
 */
export function DagHierarchyControls({
  tasks,
  edges = [],
  collapsedIds,
  onToggleCollapse,
  maxDepth = -1,
  onMaxDepthChange,
  className,
}: DagHierarchyControlsProps): React.JSX.Element {
  const validTasks = React.useMemo(
    () => (Array.isArray(tasks) ? tasks : []),
    [tasks],
  );
  const validEdges = React.useMemo(
    () => (Array.isArray(edges) ? edges : []),
    [edges],
  );

  const depths = React.useMemo(
    () => computeDepths(validTasks, validEdges),
    [validTasks, validEdges],
  );

  const visibleIds = React.useMemo(
    () => filterVisibleTasks(validTasks, validEdges, collapsedIds, maxDepth),
    [validTasks, validEdges, collapsedIds, maxDepth],
  );

  const handleDepthChange = React.useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (!onMaxDepthChange) return;
      const raw = Number(e.target.value);
      const next = Number.isFinite(raw) && raw >= 0 ? Math.floor(raw) : -1;
      onMaxDepthChange(next);
    },
    [onMaxDepthChange],
  );

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border-2 border-eb-500 bg-eb-50 p-2 text-sm",
        className,
      )}
      data-testid="dag-hierarchy-controls"
    >
      <Layers className="h-4 w-4 text-eb-500" aria-hidden />
      <span className="font-medium">階層:</span>
      <span data-testid="dag-visible-count">
        {visibleIds.size} / {validTasks.length}
      </span>
      <span className="text-gray-500" data-testid="dag-max-depth">
        max depth: {maxDepth < 0 ? "∞" : maxDepth}
      </span>
      <input
        type="number"
        min={0}
        max={MAX_REASONABLE_DEPTH}
        value={maxDepth < 0 ? "" : maxDepth}
        onChange={handleDepthChange}
        placeholder="all"
        className="ml-2 w-20 rounded border border-eb-200 bg-white px-2 py-1"
        data-testid="dag-depth-input"
      />
      <span className="ml-auto text-xs text-gray-500" data-testid="dag-collapsed-count">
        collapsed: {collapsedIds.size}
      </span>
    </div>
  );
}

/**
 * 個別 node の collapse toggle button (DAG 上に重ねる).
 */
export function CollapseButton({
  taskId,
  collapsed,
  onClick,
  className,
}: {
  taskId: number;
  collapsed: boolean;
  onClick?: (id: number) => void;
  className?: string;
}): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={() => onClick?.(taskId)}
      className={cn(
        "inline-flex items-center justify-center rounded-sm p-0.5 text-eb-500 hover:bg-eb-50",
        className,
      )}
      data-testid={`dag-collapse-${taskId}`}
      aria-label={collapsed ? "Expand" : "Collapse"}
      aria-expanded={!collapsed}
    >
      {collapsed ? (
        <ChevronRight className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <ChevronDown className="h-3.5 w-3.5" aria-hidden />
      )}
    </button>
  );
}

// Test-only exports
export const __testing__ = {
  MAX_REASONABLE_DEPTH,
  computeDepths,
  filterVisibleTasks,
};
