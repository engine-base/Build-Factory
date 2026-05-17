/**
 * T-V3-C-57-2 / S-027 — Drop zone column.
 *
 * AC-S2 (UBIQUITOUS): During a drag, valid same-feature drop zones render
 *   a dashed `eb-500` border ring. Invalid zones (different feature) stay
 *   neutral and do not receive drops.
 *
 * Re-exported via `frontend/components/kanban/DropZone.tsx` (ticket alias).
 */

"use client";

import * as React from "react";
import type { KanbanColumn } from "@/lib/api/kanban-move";

export type DropZoneProps = {
  featureId: string;
  column: KanbanColumn;
  /** True when a drag is in flight AND this zone is a valid target. */
  isValidTarget: boolean;
  /** True when a drag is in flight regardless of validity. */
  isDragActive: boolean;
  /**
   * Called when the user releases a card over this zone. The hook
   * (`useTaskDnd`) decides whether to apply, revert, or open a confirm.
   */
  onDropHere: (target: { feature_id: string; column: KanbanColumn }, opts: { shiftKey: boolean }) => void;
  children?: React.ReactNode;
};

export function DropZone(props: DropZoneProps): React.ReactElement {
  const { featureId, column, isValidTarget, isDragActive, onDropHere, children } = props;
  const [hover, setHover] = React.useState(false);

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    if (!isValidTarget) return;
    // Calling preventDefault is required by the HTML5 spec to accept the drop.
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (!hover) setHover(true);
  };

  const handleDragLeave = () => {
    if (hover) setHover(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    if (!isValidTarget) {
      // AC-F2 safeguard: never propagate a drop to an invalid target.
      e.preventDefault();
      setHover(false);
      return;
    }
    e.preventDefault();
    setHover(false);
    onDropHere({ feature_id: featureId, column }, { shiftKey: e.shiftKey });
  };

  // AC-S2: dashed eb-500 ring only when this is a valid target AND a drag
  // is active. The hover class deepens to filled tint to signal landing.
  const ringClass = isDragActive && isValidTarget
    ? hover
      ? "border-dashed border-2 border-eb-500 bg-eb-50/40"
      : "border-dashed border-2 border-eb-500"
    : "border border-slate-200";

  return (
    <div
      role="region"
      aria-label={`drop-zone-${featureId}-${column}`}
      data-feature-id={featureId}
      data-column={column}
      data-valid-target={isDragActive ? (isValidTarget ? "true" : "false") : undefined}
      data-testid={`drop-zone-${featureId}-${column}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`rounded-md p-2 min-h-[80px] transition-colors ${ringClass}`}
    >
      {children}
    </div>
  );
}
