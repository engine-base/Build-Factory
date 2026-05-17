"use client";

/**
 * T-V3-C-57-3 / S-027 — FeatureToggle: feature-pill toggle used in the
 * KanbanFilterBar feature multi-select.
 *
 * Canonical path:
 *   frontend/src/app/(app)/task/kanban/feature-toggle.tsx
 *
 * Ticket-mandated alias:
 *   frontend/components/kanban/FeatureToggle.tsx (re-exports default).
 *
 * Separated from `filter.tsx` to keep the FilterBar shell small and to give the
 * page a re-usable feature pill that can also be embedded inside an accordion
 * header (T-V3-C-57-1 wiring).
 */

import * as React from "react";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export interface FeatureToggleProps {
  featureId: string;
  label: string;
  /** When true, renders as "on" (eb-500 fill). */
  selected: boolean;
  /** Optional task counter rendered as a mono badge. */
  count?: number;
  onToggle: (featureId: string) => void;
  className?: string;
}

export function FeatureToggle({
  featureId,
  label,
  selected,
  count,
  onToggle,
  className,
}: FeatureToggleProps) {
  return (
    <button
      type="button"
      data-testid={`kanban-feature-toggle-${featureId}`}
      aria-pressed={selected}
      onClick={() => onToggle(featureId)}
      className={cn(
        "inline-flex items-center gap-1.5 text-[11px] h-7 px-2.5 rounded-full border transition-colors",
        selected
          ? "bg-eb-500 text-white border-eb-500"
          : "bg-white text-slate-700 border-slate-200 hover:border-eb-400",
        className,
      )}
    >
      {selected && <Check className="w-3 h-3" aria-hidden />}
      <span className="mono">{featureId}</span>
      <span className="font-semibold">{label}</span>
      {typeof count === "number" && (
        <span
          className={cn(
            "ml-1 mono text-[10px] font-bold px-1.5 py-0.5 rounded-full",
            selected
              ? "bg-white/20 text-white"
              : "bg-slate-100 text-slate-600",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

export default FeatureToggle;
