/**
 * T-V3-C-57-2 / S-027 — Draggable task card.
 *
 * AC-S1 (STATE-DRIVEN): While being dragged, the card carries
 *   `data-dragging="true"` and a drop-shadow (elevation/2 from
 *   design-tokens.md §6).
 *
 * Re-exported via `frontend/components/kanban/DraggableCard.tsx` (ticket
 * alias).
 */

"use client";

import * as React from "react";
import type { DragSource } from "@/lib/hooks/use-task-dnd";
import type { KanbanColumn } from "@/lib/api/kanban-move";

export type DraggableCardProps = {
  taskId: string;
  featureId: string;
  column: KanbanColumn;
  title: string;
  /** Started a drag (caller registers in use-task-dnd). */
  onDragStart: (src: DragSource) => void;
  /** Ended a drag (drop landed or cancelled). */
  onDragEnd: () => void;
  /** True while this exact card is the active drag source. */
  isDragging?: boolean;
  /** Optional id click handler (open detail drawer). */
  onClick?: () => void;
};

/**
 * Native HTML5 drag-and-drop. No extra dependency surface.
 *
 * Design-tokens.md §6 elevation/2 = `shadow-md ring-1 ring-eb-500/30`.
 * We apply both classes only when `data-dragging="true"` so the rest of
 * the time the card stays a flat 1-px slate-200 surface (matching the
 * mock at docs/mocks/2026-05-15_v3/task/S-027-task-kanban.html).
 */
export function DraggableCard(props: DraggableCardProps): React.ReactElement {
  const { taskId, featureId, column, title, onDragStart, onDragEnd, isDragging, onClick } = props;

  const handleDragStart = React.useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      // Tag payload with task_id so screen readers / inspectors can see it.
      try {
        e.dataTransfer.setData("text/x-task-id", taskId);
        e.dataTransfer.setData("text/plain", taskId);
        e.dataTransfer.effectAllowed = "move";
      } catch {
        // jsdom / older browsers may throw — non-fatal.
      }
      onDragStart({ task_id: taskId, feature_id: featureId, column });
    },
    [taskId, featureId, column, onDragStart],
  );

  const handleDragEnd = React.useCallback(() => {
    onDragEnd();
  }, [onDragEnd]);

  const dragging = isDragging ? true : undefined;

  return (
    <div
      role="button"
      tabIndex={0}
      draggable
      data-dragging={dragging ? "true" : undefined}
      data-task-id={taskId}
      data-feature-id={featureId}
      data-column={column}
      data-testid={`kanban-card-${taskId}`}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          onClick?.();
        }
      }}
      className={
        "bg-white border border-slate-200 rounded-md p-2.5 cursor-grab " +
        "hover:border-eb-500 transition-colors " +
        (dragging ? "shadow-md ring-1 ring-eb-500/30 opacity-90 cursor-grabbing" : "")
      }
    >
      <div className="text-[10px] mono text-slate-500 mb-1">{taskId}</div>
      <div className="text-xs font-semibold mb-1">{title}</div>
    </div>
  );
}
