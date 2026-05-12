"use client";

/**
 * T-010d-02: Swarm Grid UI (4×4 default + 4/9/16/64 preset + virtualization).
 *
 * 並列 swarm session を grid で visualize する component.
 * cell click で /sessions/[id] へ遷移 (page 側 onCellClick で実装).
 *
 * 4 status palette (CLAUDE.md §5.2):
 *   running   → border-eb-500
 *   done      → border-eb-700
 *   crashed   → border-rose-500
 *   paused    → border-amber-500
 *
 * size > 16 (64) で windowing: useMemo + visible slice で 16 cells/frame.
 *
 * REUSE invariant:
 *   - SwarmSessionStatus は @/lib/api/sessions から import (再定義禁止 / G15).
 *   - SwarmSessionDetail と同 palette (cross-component 一致).
 *   - no langgraph / langchain / litellm / reactflow.
 */

import * as React from "react";
import {
  Activity, CheckCircle2, AlertTriangle, PauseCircle,
  ChevronLeft, ChevronRight,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { SwarmSessionStatus } from "@/lib/api/sessions";

export type SwarmGridSize = "4" | "9" | "16" | "64";

export interface SwarmCell {
  session_id: number;
  status: SwarmSessionStatus | string;
  pool_id: number;
  cell_index: number;
  label?: string;
}

interface SwarmGridProps {
  cells: SwarmCell[];
  size?: SwarmGridSize;
  onCellClick?: (cell: SwarmCell) => void;
  className?: string;
}

// 4 status palette (SwarmSessionDetail と同期 / G15 cross-component 一致).
const STATUS_BORDER: Record<SwarmSessionStatus, string> = {
  running: "border-eb-500",
  done: "border-eb-700",
  crashed: "border-rose-500",
  paused: "border-amber-500",
};

const STATUS_BG: Record<SwarmSessionStatus, string> = {
  running: "bg-eb-50",
  done: "bg-eb-100",
  crashed: "bg-rose-50",
  paused: "bg-amber-50",
};

const STATUS_ICON: Record<SwarmSessionStatus, React.ElementType> = {
  running: Activity,
  done: CheckCircle2,
  crashed: AlertTriangle,
  paused: PauseCircle,
};

const SIZE_TO_COLS: Record<SwarmGridSize, number> = {
  "4": 2,
  "9": 3,
  "16": 4,
  "64": 8,
};

const VALID_SIZES: SwarmGridSize[] = ["4", "9", "16", "64"];

// 仮想化 threshold: size 64 で windowing.
const VIRTUALIZATION_THRESHOLD = 16;
const WINDOW_PAGE = 16;

function isKnownStatus(s: string): s is SwarmSessionStatus {
  return s === "running" || s === "done" || s === "crashed" || s === "paused";
}

export function SwarmGrid({
  cells,
  size = "16",
  onCellClick,
  className,
}: SwarmGridProps) {
  // graceful fallback (AC-4): unknown size → default 16
  const effectiveSize: SwarmGridSize = VALID_SIZES.includes(size)
    ? size
    : "16";
  const sizeNum = Number(effectiveSize);
  const cols = SIZE_TO_COLS[effectiveSize];

  // AC-4: cells > size はクリップ (graceful overflow)
  const clippedCells = React.useMemo(
    () => cells.slice(0, sizeNum),
    [cells, sizeNum],
  );

  // 仮想化: size > 16 (= 64) で windowing
  const [windowStart, setWindowStart] = React.useState(0);
  const isVirtualized = sizeNum > VIRTUALIZATION_THRESHOLD;

  const visibleCells = React.useMemo(() => {
    if (!isVirtualized) return clippedCells;
    return clippedCells.slice(windowStart, windowStart + WINDOW_PAGE);
  }, [isVirtualized, clippedCells, windowStart]);

  const handleClick = React.useCallback(
    (cell: SwarmCell) => {
      onCellClick?.(cell);
    },
    [onCellClick],
  );

  // size 4 -> grid-cols-2 / 9 -> 3 / 16 -> 4 / 64 -> 8
  const gridColsClass =
    cols === 2 ? "grid-cols-2" :
    cols === 3 ? "grid-cols-3" :
    cols === 4 ? "grid-cols-4" :
    "grid-cols-8";

  return (
    <div
      className={cn("flex flex-col gap-2", className)}
      data-testid="swarm-grid"
      data-size={effectiveSize}
    >
      {isVirtualized ? (
        <div
          className="flex items-center justify-between text-xs text-slate-500"
          data-testid="swarm-grid-window-controls"
        >
          <span>
            cells {windowStart + 1}–{Math.min(windowStart + WINDOW_PAGE, clippedCells.length)} of {clippedCells.length}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              className="inline-flex items-center gap-0.5 rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-50 disabled:opacity-50"
              onClick={() => setWindowStart(Math.max(0, windowStart - WINDOW_PAGE))}
              disabled={windowStart === 0}
              aria-label="previous page"
            >
              <ChevronLeft className="h-3 w-3" /> prev
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-0.5 rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-50 disabled:opacity-50"
              onClick={() =>
                setWindowStart(
                  Math.min(
                    Math.max(0, clippedCells.length - WINDOW_PAGE),
                    windowStart + WINDOW_PAGE,
                  ),
                )
              }
              disabled={windowStart + WINDOW_PAGE >= clippedCells.length}
              aria-label="next page"
            >
              next <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        </div>
      ) : null}

      <div
        className={cn("grid gap-2", gridColsClass)}
        role="grid"
        aria-label={`swarm grid ${effectiveSize}`}
      >
        {visibleCells.map((cell, idx) => {
          const rawStatus = String(cell.status ?? "running");
          const status: SwarmSessionStatus = isKnownStatus(rawStatus)
            ? rawStatus
            : "running";
          const Icon = STATUS_ICON[status];
          return (
            <button
              key={`${cell.pool_id}-${cell.cell_index}-${idx}`}
              type="button"
              role="gridcell"
              data-testid="swarm-grid-cell"
              data-status={status}
              data-session-id={cell.session_id}
              className={cn(
                "flex aspect-square flex-col items-center justify-center rounded border-2 p-2 text-xs hover:shadow",
                STATUS_BORDER[status],
                STATUS_BG[status],
              )}
              onClick={() => handleClick(cell)}
            >
              <Icon className="h-4 w-4" />
              <span className="mt-1 font-mono">#{cell.session_id}</span>
              {cell.label ? (
                <span className="mt-0.5 text-[10px] text-slate-600">
                  {cell.label.slice(0, 12)}
                </span>
              ) : null}
            </button>
          );
        })}
        {/* empty slots (cells.length < size) */}
        {Array.from({ length: Math.max(0, (isVirtualized ? WINDOW_PAGE : sizeNum) - visibleCells.length) }).map((_, i) => (
          <div
            key={`empty-${i}`}
            data-testid="swarm-grid-empty-slot"
            className="aspect-square rounded border-2 border-dashed border-slate-200 bg-slate-50"
          />
        ))}
      </div>
    </div>
  );
}

export default SwarmGrid;
