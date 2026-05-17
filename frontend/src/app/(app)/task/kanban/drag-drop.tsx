/**
 * T-V3-C-57-2 / S-027 — Kanban drag & drop integration layer.
 *
 * Mounted by the page.tsx that T-V3-C-57-1 owns. Kept in a separate file
 * (per the C-57-1 ↔ C-57-2 file mutex in tickets-group-c-ui-part2.json) so
 * the two work packages can land in any order without rebase conflict.
 *
 * Usage from C-57-1's page.tsx (illustrative; C-57-1 wires the actual
 * mount):
 *
 *   import { KanbanDndProvider } from "./drag-drop";
 *
 *   <KanbanDndProvider initial={cards}>
 *     {(ctx) => (
 *       <AccordionBoard {...ctx} />
 *     )}
 *   </KanbanDndProvider>
 *
 * This file owns:
 *   - the optimistic state via useTaskDnd
 *   - the toast surface wiring (`sonner.toast.error`)
 *   - the shift+drop confirm (AC-F4) using a native `window.confirm`
 *
 * It deliberately does NOT render the accordion / columns / cards (that's
 * C-57-1's surface). It exposes `useTaskDnd`'s return value as a render
 * prop / context value.
 */

"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  KanbanCard,
  UseTaskDndResult,
  useTaskDnd,
} from "@/lib/hooks/use-task-dnd";

export type KanbanDndContextValue = UseTaskDndResult;

const KanbanDndContext = React.createContext<KanbanDndContextValue | null>(null);

export function useKanbanDnd(): KanbanDndContextValue {
  const ctx = React.useContext(KanbanDndContext);
  if (!ctx) {
    throw new Error(
      "useKanbanDnd() must be used inside <KanbanDndProvider>. " +
        "Wrap the S-027 board in KanbanDndProvider before mounting cards.",
    );
  }
  return ctx;
}

export type KanbanDndProviderProps = {
  initial: ReadonlyArray<KanbanCard>;
  /**
   * Optional render-prop alternative to the context. Useful for stories
   * that need to inspect drag state without consuming the context.
   */
  children?: React.ReactNode | ((ctx: KanbanDndContextValue) => React.ReactNode);
  /**
   * Override the toast surface. Defaults to `sonner.toast.error`.
   * Test harness passes a mock here.
   */
  onErrorToast?: (msg: string) => void;
  /**
   * Override the shift+drop confirm gate. Defaults to `window.confirm`.
   */
  onShiftConfirm?: (req: { task_id: string; new_column: string }) => Promise<boolean>;
};

export function KanbanDndProvider(props: KanbanDndProviderProps): React.ReactElement {
  const defaultToast = React.useCallback((msg: string) => {
    toast.error(msg);
  }, []);
  const defaultConfirm = React.useCallback(
    async (req: { task_id: string; new_column: string }): Promise<boolean> => {
      if (typeof window === "undefined") return true;
      return window.confirm(
        `Move ${req.task_id} to ${req.new_column}? (shift-drop confirmation — AC-F4)`,
      );
    },
    [],
  );

  const value = useTaskDnd({
    initial: props.initial,
    onErrorToast: props.onErrorToast ?? defaultToast,
    onShiftConfirm: props.onShiftConfirm ?? defaultConfirm,
  });

  return (
    <KanbanDndContext.Provider value={value}>
      {typeof props.children === "function" ? props.children(value) : props.children}
    </KanbanDndContext.Provider>
  );
}
