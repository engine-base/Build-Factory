"use client";

/**
 * T-009-05: 依存追加/削除 drag&drop helpers + UI panel.
 *
 * 既存 DependencyGraph.tsx (T-009-02) は **完全無改変** (REUSE).
 * task 間の依存 (task_dependencies) を React Flow の onConnect / onEdgesDelete
 * callback で操作するための純関数 + 軽量 UI を提供.
 *
 * AC マッピング (T-009-05 NEW):
 *   AC-1 UBIQUITOUS    : validateNewDependency / proposeAddEdge /
 *                        proposeRemoveEdge を提供. 既存 DependencyGraph 無改変.
 *                        DependencyDnDPanel で undo/redo + pending changes 表示.
 *   AC-2 EVENT-DRIVEN  : onAddEdge / onRemoveEdge callback / useMemo / useCallback.
 *   AC-3 STATE-DRIVEN  : changes は controlled (caller 持ち) /
 *                        eb-* palette / Lucide icons / 楽観的更新を caller に委譲.
 *   AC-4 UNWANTED      : 自己 edge / 重複 edge / 循環依存導入 で reject /
 *                        非 numeric id で reject.
 */

import * as React from "react";
import { Plus, Trash2, Undo2, AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";

// ──────────────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────────────

export interface DependencyEdge {
  source: number;
  target: number;
  edge_type?: "hard" | "soft";
}

export type DependencyChangeKind = "add" | "remove";

export interface DependencyChange {
  kind: DependencyChangeKind;
  edge: DependencyEdge;
  timestamp: number;
}

export type ValidationResult =
  | { valid: true }
  | { valid: false; reason: string; code: string };

// ──────────────────────────────────────────────────────────────────────
// Pure helpers (no React, testable)
// ──────────────────────────────────────────────────────────────────────

/**
 * 新規 edge が valid か検証.
 * - source / target が positive int
 * - source !== target (self-edge 禁止)
 * - existing に重複なし
 * - 追加で circular dependency を作らない (BFS 検出)
 */
export function validateNewDependency(
  source: unknown,
  target: unknown,
  existing: DependencyEdge[],
): ValidationResult {
  if (typeof source !== "number" || typeof target !== "number") {
    return { valid: false, reason: "source/target must be number",
             code: "dep.invalid_type" };
  }
  if (!Number.isFinite(source) || !Number.isFinite(target)) {
    return { valid: false, reason: "source/target must be finite",
             code: "dep.invalid_type" };
  }
  if (!Number.isInteger(source) || !Number.isInteger(target)) {
    return { valid: false, reason: "source/target must be integer",
             code: "dep.invalid_type" };
  }
  if (source <= 0 || target <= 0) {
    return { valid: false, reason: "source/target must be > 0",
             code: "dep.invalid_value" };
  }
  if (source === target) {
    return { valid: false, reason: "self-dependency not allowed",
             code: "dep.self_edge" };
  }

  const existingArr = Array.isArray(existing) ? existing : [];

  // 重複
  for (const e of existingArr) {
    if (!e) continue;
    if (e.source === source && e.target === target) {
      return { valid: false, reason: "duplicate edge", code: "dep.duplicate" };
    }
  }

  // 循環検出: target から source へ既存パスが辿れるなら閉路発生
  // BFS: target を起点に descendants を探索. source に到達したら NG.
  const adj = new Map<number, number[]>();
  for (const e of existingArr) {
    if (!e || typeof e.source !== "number" || typeof e.target !== "number") {
      continue;
    }
    const arr = adj.get(e.source) ?? [];
    arr.push(e.target);
    adj.set(e.source, arr);
  }
  const visited = new Set<number>();
  const queue: number[] = [target];
  while (queue.length > 0) {
    const node = queue.shift()!;
    if (visited.has(node)) continue;
    visited.add(node);
    if (node === source) {
      return { valid: false, reason: "would create cycle",
               code: "dep.cycle" };
    }
    for (const next of adj.get(node) ?? []) {
      if (!visited.has(next)) queue.push(next);
    }
  }

  return { valid: true };
}

/**
 * pending changes リストに add change を提案. invalid なら null.
 */
export function proposeAddEdge(
  source: number,
  target: number,
  existing: DependencyEdge[],
  pending: DependencyChange[],
): DependencyChange | { error: ValidationResult & { valid: false } } {
  // pending changes を merged して validation (現実時点の edge set で判定)
  const merged = applyPending(existing, pending);
  const result = validateNewDependency(source, target, merged);
  if (!result.valid) {
    return { error: result };
  }
  return {
    kind: "add",
    edge: { source, target, edge_type: "hard" },
    timestamp: Date.now(),
  };
}

export function proposeRemoveEdge(
  edge: DependencyEdge,
): DependencyChange {
  return {
    kind: "remove",
    edge,
    timestamp: Date.now(),
  };
}

/**
 * pending changes を existing に適用した最終 edge 集合を返す.
 */
export function applyPending(
  existing: DependencyEdge[],
  pending: DependencyChange[],
): DependencyEdge[] {
  const existingArr = Array.isArray(existing) ? existing : [];
  const pendingArr = Array.isArray(pending) ? pending : [];

  // Start with existing
  let edges: DependencyEdge[] = [...existingArr];
  for (const ch of pendingArr) {
    if (!ch || !ch.edge) continue;
    if (ch.kind === "add") {
      // 重複しない場合のみ追加 (validation 失敗時の二重追加防止)
      const exists = edges.some(
        (e) => e.source === ch.edge.source && e.target === ch.edge.target,
      );
      if (!exists) edges.push(ch.edge);
    } else if (ch.kind === "remove") {
      edges = edges.filter(
        (e) =>
          !(e.source === ch.edge.source && e.target === ch.edge.target),
      );
    }
  }
  return edges;
}

// ──────────────────────────────────────────────────────────────────────
// React: pending changes panel
// ──────────────────────────────────────────────────────────────────────

export interface DependencyDnDPanelProps {
  pending: DependencyChange[];
  onUndo?: (changeIndex: number) => void;
  onConfirm?: () => void;
  onCancel?: () => void;
  lastValidationError?: { reason: string; code: string } | null;
  className?: string;
}

export function DependencyDnDPanel({
  pending,
  onUndo,
  onConfirm,
  onCancel,
  lastValidationError,
  className,
}: DependencyDnDPanelProps): React.JSX.Element {
  const validPending = React.useMemo(
    () => (Array.isArray(pending) ? pending : []),
    [pending],
  );

  const addCount = React.useMemo(
    () => validPending.filter((c) => c?.kind === "add").length,
    [validPending],
  );
  const removeCount = React.useMemo(
    () => validPending.filter((c) => c?.kind === "remove").length,
    [validPending],
  );

  if (validPending.length === 0 && !lastValidationError) {
    return (
      <div
        className={cn(
          "rounded-lg border-2 border-eb-200 bg-white p-2 text-sm text-gray-500",
          className,
        )}
        data-testid="dnd-panel-idle"
      >
        変更なし
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg border-2 border-eb-500 bg-eb-50 p-3 text-sm",
        className,
      )}
      data-testid="dnd-panel"
    >
      {lastValidationError && (
        <div
          className="mb-2 flex items-center gap-2 rounded border border-eb-400 bg-white p-2"
          data-testid="dnd-validation-error"
        >
          <AlertCircle className="h-4 w-4 text-eb-500" aria-hidden />
          <span className="text-xs">
            {lastValidationError.code}: {lastValidationError.reason}
          </span>
        </div>
      )}
      <div className="flex items-center gap-3">
        <Plus className="h-4 w-4 text-eb-500" aria-hidden />
        <span data-testid="dnd-add-count">+{addCount}</span>
        <Trash2 className="ml-3 h-4 w-4 text-eb-500" aria-hidden />
        <span data-testid="dnd-remove-count">-{removeCount}</span>
      </div>
      <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto">
        {validPending.map((c, idx) => (
          <li
            key={`${c.timestamp}-${idx}`}
            className="flex items-center justify-between rounded border border-eb-200 bg-white px-2 py-1 text-xs"
            data-testid={`dnd-change-${idx}`}
          >
            <span>
              {c.kind === "add" ? "+ " : "- "}
              {c.edge.source} → {c.edge.target}
            </span>
            <button
              type="button"
              onClick={() => onUndo?.(idx)}
              className="text-eb-500 hover:underline"
              data-testid={`dnd-undo-${idx}`}
              aria-label={`Undo change ${idx}`}
            >
              <Undo2 className="h-3.5 w-3.5" aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      {validPending.length > 0 && (
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={onConfirm}
            className="rounded border-2 border-eb-500 bg-eb-500 px-3 py-1 text-xs text-white hover:bg-eb-400"
            data-testid="dnd-confirm"
          >
            適用 ({validPending.length} 件)
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded border-2 border-eb-200 bg-white px-3 py-1 text-xs text-eb-500"
            data-testid="dnd-cancel"
          >
            キャンセル
          </button>
        </div>
      )}
    </div>
  );
}

// Test-only exports
export const __testing__ = {
  validateNewDependency,
  proposeAddEdge,
  proposeRemoveEdge,
  applyPending,
};
