/**
 * T-V3-C-57-2 / S-027 — Kanban drag & drop hook.
 *
 * Canonical implementation. Re-exported via
 * `frontend/lib/hooks/use-task-dnd.ts` (ticket-mandated alias).
 *
 * Responsibilities:
 *   - track in-flight drag state (which task, which source feature/column)
 *   - validate drop targets (same-feature rule per AC-F2)
 *   - optimistically apply the move within the same React render tick (<100ms)
 *   - call PATCH /api/tasks/{id} via `moveTask()`, revert on 4xx
 *   - surface 409 inline (AC-F3)
 *   - guard shift-drop with confirm dialog (AC-F4)
 *
 * Implementation note: HTML5 native drag-and-drop is used (no dnd-kit
 * dependency added) so this hook works inside the existing Build-Factory
 * frontend bundle without expanding the package surface.
 */

"use client";

import { useCallback, useState } from "react";
import {
  KANBAN_STATUS_BY_COLUMN,
  KanbanColumn,
  KanbanMoveError,
  moveTask,
} from "@/lib/api/kanban-move";

export type KanbanCard = {
  task_id: string;
  feature_id: string;
  column: KanbanColumn;
  title?: string;
};

export type DragSource = {
  task_id: string;
  feature_id: string;
  column: KanbanColumn;
};

export type DropOutcome =
  | { kind: "applied"; task_id: string; new_column: KanbanColumn }
  | { kind: "rejected"; reason: "different_feature" | "same_position" }
  | { kind: "reverted"; task_id: string; status: number; endpoint: string; code?: string }
  | { kind: "needs_confirm"; task_id: string; new_column: KanbanColumn };

export type UseTaskDndArgs = {
  /**
   * Initial cards (typically supplied by use-kanban-board / fetch).
   */
  initial: ReadonlyArray<KanbanCard>;
  /**
   * Toast surface for revert / 409 messages. Caller supplies `sonner.toast.error`
   * (or any compatible signature) to keep this hook framework-agnostic.
   */
  onErrorToast?: (message: string) => void;
  /**
   * Optional confirm hook for AC-F4 (shift+drop). When omitted, shift+drop
   * is treated as a normal drop.
   */
  onShiftConfirm?: (req: { task_id: string; new_column: KanbanColumn }) => Promise<boolean>;
};

export type UseTaskDndResult = {
  cards: ReadonlyArray<KanbanCard>;
  dragging: DragSource | null;
  /** AC-S1: STATE-DRIVEN — drag start sets `data-dragging=true` on the card. */
  onDragStart: (src: DragSource) => void;
  onDragEnd: () => void;
  /**
   * Validate drop target. Returns true when the column belongs to the SAME
   * feature accordion. Renderers should toggle the dashed eb-500 ring
   * (AC-S2) only when this returns true.
   */
  isValidDrop: (target: { feature_id: string; column: KanbanColumn }) => boolean;
  /**
   * Apply a drop. Performs optimistic update synchronously (so AC-F1's
   * 100ms-budget is structurally guaranteed) then awaits the PATCH.
   */
  onDrop: (
    target: { feature_id: string; column: KanbanColumn },
    opts?: { shiftKey?: boolean },
  ) => Promise<DropOutcome>;
};

export function useTaskDnd(args: UseTaskDndArgs): UseTaskDndResult {
  const [cards, setCards] = useState<KanbanCard[]>(() => args.initial.slice() as KanbanCard[]);
  const [dragging, setDragging] = useState<DragSource | null>(null);

  const onDragStart = useCallback((src: DragSource) => {
    setDragging(src);
  }, []);

  const onDragEnd = useCallback(() => {
    setDragging(null);
  }, []);

  const isValidDrop = useCallback(
    (target: { feature_id: string; column: KanbanColumn }) => {
      if (!dragging) return false;
      // AC-F2: must be same feature accordion.
      return dragging.feature_id === target.feature_id;
    },
    [dragging],
  );

  const performMove = useCallback(
    async (src: DragSource, target: { feature_id: string; column: KanbanColumn }): Promise<DropOutcome> => {
      // Snapshot for revert.
      const before = cards;
      // AC-F1 (optimistic): mutate UI synchronously so the visible move
      // happens in the same render tick (<100ms structural guarantee).
      const next = before.map((c) =>
        c.task_id === src.task_id && c.feature_id === src.feature_id
          ? { ...c, column: target.column }
          : c,
      );
      setCards(next);
      setDragging(null);
      try {
        await moveTask({
          task_id: src.task_id,
          feature_id: src.feature_id,
          from_column: src.column,
          to_column: target.column,
        });
        return { kind: "applied", task_id: src.task_id, new_column: target.column };
      } catch (err) {
        // Revert on 4xx/5xx.
        setCards(before);
        const e =
          err instanceof KanbanMoveError
            ? err
            : new KanbanMoveError("kanban move failed", 0, "/api/tasks/?", undefined);
        const message =
          e.status === 409
            ? `dependency block (${e.endpoint})`
            : `move failed: ${e.endpoint} (status ${e.status})`;
        args.onErrorToast?.(message);
        return {
          kind: "reverted",
          task_id: src.task_id,
          status: e.status,
          endpoint: e.endpoint,
          code: e.code,
        };
      }
    },
    [cards, args],
  );

  const onDrop = useCallback(
    async (
      target: { feature_id: string; column: KanbanColumn },
      opts?: { shiftKey?: boolean },
    ): Promise<DropOutcome> => {
      const src = dragging;
      if (!src) {
        return { kind: "rejected", reason: "same_position" };
      }
      // AC-F2: cross-feature drop is rejected, no API call.
      if (src.feature_id !== target.feature_id) {
        setDragging(null);
        return { kind: "rejected", reason: "different_feature" };
      }
      if (src.column === target.column) {
        setDragging(null);
        return { kind: "rejected", reason: "same_position" };
      }
      // AC-F4: OPTIONAL shift+drop -> confirm gate.
      if (opts?.shiftKey && args.onShiftConfirm) {
        const ok = await args.onShiftConfirm({
          task_id: src.task_id,
          new_column: target.column,
        });
        if (!ok) {
          setDragging(null);
          return { kind: "needs_confirm", task_id: src.task_id, new_column: target.column };
        }
      }
      return performMove(src, target);
    },
    [dragging, args, performMove],
  );

  return { cards, dragging, onDragStart, onDragEnd, isValidDrop, onDrop };
}

// Re-export so consumers can construct API payloads without re-importing the
// status enum from two places.
export { KANBAN_STATUS_BY_COLUMN };
