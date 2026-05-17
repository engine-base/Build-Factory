/**
 * T-V3-C-57-1 / S-027 — Kanban board hook.
 *
 * Lightweight wrapper around {@link getKanbanTasks}. Mirrors the pattern of
 * use-screen-flow-map (T-V3-C-51) so the page can stay provider-independent
 * (no QueryClientProvider required at the (app) layout for the test harness).
 *
 * AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-57-1.md):
 *   AC-F1 — getKanbanTasks GET on mount; 2xx renders tasks grouped by feature.
 *   AC-F2 — 401 surfaced via {@link KanbanApiError.status} === 401 so the page
 *           can router.replace("/login") before any workspace-scoped UI is
 *           committed.
 *   AC-F3 — `loading === true` while the GET is in flight, so the page can
 *           render the skeleton accordion with role="status" aria-live="polite".
 *   AC-F4 — 403 surfaced via `error.status === 403` so the page can mount the
 *           S-046 inline 403 instead of partial data.
 *
 * Drag & drop / filter wiring is out of scope for T-V3-C-57-1; subsequent
 * tasks (T-V3-C-57-2 / -3) extend this hook with optimistic patches and
 * filter state respectively.
 */

"use client";

import * as React from "react";

import {
  getKanbanTasks,
  KanbanApiError,
  normaliseKanbanStatus,
  type KanbanColumn,
  type KanbanTask,
  type KanbanTaskGroup,
  type KanbanTasksResponse,
} from "@/api/kanban";

// --------------------------------------------------------------------------
// Aggregated view-model — what the AccordionBoard component consumes.
// --------------------------------------------------------------------------

export interface KanbanColumnTasks {
  todo: KanbanTask[];
  in_progress: KanbanTask[];
  review: KanbanTask[];
  done: KanbanTask[];
}

export interface KanbanFeatureSection {
  /** feature_id (e.g. "F-001") or "ungrouped" for tasks without feature_id. */
  feature_id: string;
  /** Display label — falls back to feature_id when name is missing. */
  name: string;
  /** Total task count for this feature (sum of all 4 columns). */
  total: number;
  /** Per-column buckets — 4 entries, always present (possibly empty). */
  columns: KanbanColumnTasks;
  /**
   * Default-expanded if at least one task is in_progress AND the feature is
   * neither all-done nor all-todo. This realises AC-S3:
   *   "expand only in-progress feature accordions by default; completed
   *    (all Done) and not-started (all Todo) features shall be collapsed".
   */
  defaultExpanded: boolean;
}

export interface UseKanbanBoardResult {
  /** Per-feature aggregated sections. Empty array on error / before first load. */
  sections: KanbanFeatureSection[];
  /** Raw response (kept for downstream consumers that need flat lists). */
  raw: KanbanTasksResponse | null;
  loading: boolean;
  error: KanbanApiError | null;
  /** Refetch GET /tasks. */
  reload: () => Promise<void>;
}

// --------------------------------------------------------------------------
// Grouping helper — pure function, also exported for unit tests.
// --------------------------------------------------------------------------

/** Sort feature sections deterministically (group order first, then alpha). */
function sortSections(
  sections: KanbanFeatureSection[],
  groupOrder: Map<string, number>,
): KanbanFeatureSection[] {
  return [...sections].sort((a, b) => {
    const ai = groupOrder.get(a.feature_id) ?? Number.MAX_SAFE_INTEGER;
    const bi = groupOrder.get(b.feature_id) ?? Number.MAX_SAFE_INTEGER;
    if (ai !== bi) return ai - bi;
    return a.feature_id.localeCompare(b.feature_id);
  });
}

/**
 * Aggregate the raw GET /tasks response into per-feature × per-column buckets.
 * Pure function — exported for unit tests.
 */
export function aggregateKanban(
  payload: KanbanTasksResponse,
): KanbanFeatureSection[] {
  const groups: KanbanTaskGroup[] = payload.groups ?? [];
  const groupNames = new Map<string, string>();
  const groupOrder = new Map<string, number>();
  groups.forEach((g, idx) => {
    if (g?.id) {
      groupNames.set(g.id, g.name ?? g.id);
      groupOrder.set(g.id, idx);
    }
  });

  const sections = new Map<string, KanbanFeatureSection>();

  for (const task of payload.tasks ?? []) {
    const featureId =
      typeof task.feature_id === "string" && task.feature_id.length > 0
        ? task.feature_id
        : "ungrouped";

    let section = sections.get(featureId);
    if (!section) {
      section = {
        feature_id: featureId,
        name:
          groupNames.get(featureId) ??
          (featureId === "ungrouped" ? "未分類" : featureId),
        total: 0,
        columns: { todo: [], in_progress: [], review: [], done: [] },
        defaultExpanded: false,
      };
      sections.set(featureId, section);
    }
    const col: KanbanColumn = normaliseKanbanStatus(task.status);
    section.columns[col].push(task);
    section.total += 1;
  }

  // AC-S3: default-expand only when at least one task is in_progress AND the
  // feature is neither all-done nor all-todo.
  for (const section of sections.values()) {
    const inProgressCount = section.columns.in_progress.length;
    const doneCount = section.columns.done.length;
    const todoCount = section.columns.todo.length;
    const reviewCount = section.columns.review.length;
    const allDone = section.total > 0 && doneCount === section.total;
    const allTodo = section.total > 0 && todoCount === section.total;
    section.defaultExpanded =
      inProgressCount > 0 && !allDone && !allTodo
        ? true
        : reviewCount > 0 && !allDone && !allTodo;
  }

  return sortSections(Array.from(sections.values()), groupOrder);
}

// --------------------------------------------------------------------------
// Hook
// --------------------------------------------------------------------------

/**
 * useKanbanBoard — single GET /tasks?group_by=feature on mount + on workspace
 * change. The hook never throws for {@link KanbanApiError}: it stores the
 * error on `error` so the page can branch on status (401 → redirect / 403 →
 * 403 page / other → toast + empty).
 */
export function useKanbanBoard(
  workspaceId: string | number,
): UseKanbanBoardResult {
  const [raw, setRaw] = React.useState<KanbanTasksResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<KanbanApiError | null>(null);

  const reload = React.useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const payload = await getKanbanTasks(workspaceId);
      setRaw(payload);
    } catch (err) {
      if (err instanceof KanbanApiError) {
        setError(err);
        setRaw(null);
      } else {
        throw err;
      }
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  React.useEffect(() => {
    void reload();
  }, [reload]);

  const sections = React.useMemo<KanbanFeatureSection[]>(() => {
    if (!raw) return [];
    return aggregateKanban(raw);
  }, [raw]);

  return { sections, raw, loading, error, reload };
}
