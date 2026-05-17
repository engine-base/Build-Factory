/**
 * T-V3-C-59 / S-029 — Task DAG view hook.
 *
 * Lightweight wrapper around {@link getTaskDag}, {@link getTasksByFeature},
 * {@link createTaskDependency}, and {@link runImpactAnalysis}. Follows the
 * provider-independent pattern established by use-screen-flow-map.ts so the
 * page can stay free of QueryClientProvider wiring in tests.
 *
 * AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-59.md):
 *   AC-F1 (S-029) — getTaskDag GET on mount; 4xx → page renders toast + empty.
 *   AC-F2 (S-029) — 401 surfaced via {@link TaskDagApiError.status} === 401 so
 *                   the page can router.replace("/login") before any
 *                   workspace-scoped UI is committed.
 *   AC-F3 (S-029) — getTasksByFeature returns accordion-friendly groups.
 *   AC-F4 (S-029) — createTaskDependency persists a new edge.
 */

"use client";

import * as React from "react";

import {
  createTaskDependency,
  getTaskDag,
  getTasksByFeature,
  runImpactAnalysis,
  TaskDagApiError,
  type DependencyCreatePayload,
  type DependencyCreateResponse,
  type ImpactAnalysisPayload,
  type ImpactAnalysisResponse,
  type TaskDagResponse,
  type TasksByFeatureResponse,
} from "@/api/task-dag";

export interface UseTaskDagViewResult {
  data: TaskDagResponse | null;
  byFeature: TasksByFeatureResponse | null;
  loading: boolean;
  error: TaskDagApiError | null;
  /** Refetch GET /tasks/dag (and the feature-grouped projection). */
  reload: () => Promise<void>;
  /** AC-F4: POST /dependencies — caller catches TaskDagApiError. */
  addDependency: (
    body: DependencyCreatePayload,
  ) => Promise<DependencyCreateResponse>;
  /** Impact analysis side-panel data — caller catches TaskDagApiError. */
  analyzeImpact: (
    body: ImpactAnalysisPayload,
  ) => Promise<ImpactAnalysisResponse>;
}

/**
 * useTaskDagView — GET /tasks/dag + /tasks?group_by=feature on mount.
 *
 * Test seam: routes all network calls through the @/api/task-dag helpers
 * which rely on `globalThis.fetch` by default. Vitest can mock that fetch to
 * drive the 200 / 401 / 4xx branches.
 */
export function useTaskDagView(
  workspaceId: string | number,
): UseTaskDagViewResult {
  const [data, setData] = React.useState<TaskDagResponse | null>(null);
  const [byFeature, setByFeature] =
    React.useState<TasksByFeatureResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<TaskDagApiError | null>(null);

  const reload = React.useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const dagPayload = await getTaskDag(workspaceId);
      setData(dagPayload);
      // AC-F3: also fetch grouped projection. Failure here should not nuke
      // the DAG payload — surface only via byFeature === null.
      try {
        const groups = await getTasksByFeature(workspaceId);
        setByFeature(groups);
      } catch (err) {
        if (err instanceof TaskDagApiError) {
          // 401 must propagate so page redirects; other 4xx → silent for the
          // accordion, the main DAG still renders.
          if (err.status === 401) {
            setError(err);
            setData(null);
            setByFeature(null);
            return;
          }
          setByFeature(null);
        } else {
          throw err;
        }
      }
    } catch (err) {
      if (err instanceof TaskDagApiError) {
        setError(err);
        setData(null);
        setByFeature(null);
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

  const addDependency = React.useCallback(
    (body: DependencyCreatePayload): Promise<DependencyCreateResponse> => {
      return createTaskDependency(workspaceId, body);
    },
    [workspaceId],
  );

  const analyzeImpact = React.useCallback(
    (body: ImpactAnalysisPayload): Promise<ImpactAnalysisResponse> => {
      return runImpactAnalysis(workspaceId, body);
    },
    [workspaceId],
  );

  return {
    data,
    byFeature,
    loading,
    error,
    reload,
    addDependency,
    analyzeImpact,
  };
}
