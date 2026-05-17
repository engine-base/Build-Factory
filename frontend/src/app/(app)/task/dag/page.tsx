"use client";

/**
 * S-029 タスク DAG — T-V3-C-59 / F-007.
 *
 * @screen-id S-029
 * @feature-id F-007
 * @task-ids T-V3-C-59,T-V3-RF-13,T-V3-FIX-03
 * @entities E-018,E-019
 * @phase Phase 1
 *
 * Implements the v3 mock at:
 *   docs/mocks/2026-05-15_v3/task/S-029-task-dag-view.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-59.md):
 *   structural.AC-S1 (h1 == "タスク DAG" / mock h1 逐語)               — page heading.
 *   structural.AC-S2 (Lucide icons exclusively / no emoji glyphs)      — Lucide imports below.
 *   functional.AC-F1 (EVENT-DRIVEN GET /api/workspaces/{id}/tasks/dag on mount;
 *     2xx renders into the page / 4xx → inline error toast + empty state) —
 *     useTaskDagView hook on mount.
 *   functional.AC-F2 (UNWANTED: unauthenticated → redirect /login (S-001) /
 *     never render workspace-scoped data) — useRouter().replace("/login") on 401.
 *   functional.AC-F3 (EVENT-DRIVEN GET /api/workspaces/{id}/tasks?group_by=feature
 *     returns tasks grouped by feature_id with accordion-friendly metadata) —
 *     useTaskDagView.byFeature populates the feature accordion.
 *   functional.AC-F4 (EVENT-DRIVEN POST /api/workspaces/{id}/dependencies with a
 *     valid edge persists it and returns 200) — handleAddDependency dispatches
 *     createTaskDependency + impact-analysis side panel.
 *
 * Backend contract: T-V3-B-007 (tasks/dag) + T-V3-B-014 (dependencies / impact).
 *
 * Workspace scoping: page reads ?workspace_id from the search params, defaulting
 * to "active". The (app) layout will supply it from the active workspace once
 * that wiring lands.
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  FileText,
  GitBranch,
  Grid3x3,
  Kanban,
  LayoutDashboard,
  List,
  Maximize,
  Minus,
  Plus,
  Workflow,
} from "lucide-react";

import {
  TaskDagApiError,
  type ImpactAnalysisResponse,
  type TaskDagEdge,
  type TaskDagNode,
  type TasksByFeatureGroup,
} from "@/api/task-dag";
import { useTaskDagView } from "@/hooks/use-task-dag-view";

// --------------------------------------------------------------------------
// Mock-derived literals — 逐語 from docs/mocks/2026-05-15_v3/task/S-029-*.html
// --------------------------------------------------------------------------

const S029_H1_TEXT = "タスク DAG";
const S029_SUBTITLE =
  "タスク間の依存関係を React Flow で可視化 / Phase / Status で fillter";

// --------------------------------------------------------------------------
// Layout helper — distribute nodes deterministically into a grid so we never
// require a runtime layout engine for the smoke test. Wave 2 will swap this
// for @xyflow/react.
// --------------------------------------------------------------------------

interface PositionedNode extends TaskDagNode {
  x: number;
  y: number;
}

function layoutNodes(nodes: TaskDagNode[]): PositionedNode[] {
  const NODE_W = 140;
  const NODE_H = 72;
  const GAP_X = 80;
  const GAP_Y = 48;
  const COLS = 6;
  return nodes.map((n, idx) => {
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    return {
      ...n,
      x: 60 + col * (NODE_W + GAP_X),
      y: 70 + row * (NODE_H + GAP_Y),
    };
  });
}

function statusBorder(status?: string): string {
  switch (status) {
    case "done":
      return "border-2 border-emerald-500";
    case "running":
      return "border-2 border-amber-300 ring-2 ring-amber-100";
    case "blocked":
      return "border-2 border-red-300 ring-2 ring-red-100";
    default:
      return "border border-slate-300";
  }
}

function statusPill(status?: string): string {
  switch (status) {
    case "done":
      return "bg-emerald-50 text-emerald-700";
    case "running":
      return "bg-amber-50 text-amber-700";
    case "blocked":
      return "bg-red-50 text-red-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

function edgeStroke(type?: string | null): string {
  if (type === "blocks") return "#dc2626";
  if (type === "soft" || type === "informs") return "#94a3b8";
  return "#1a6648";
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function TaskDagViewPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams?.get("workspace_id") ?? "active";

  const {
    data,
    byFeature,
    loading,
    error,
    reload,
    addDependency,
    analyzeImpact,
  } = useTaskDagView(workspaceId);

  const [openFeatureIds, setOpenFeatureIds] = React.useState<Set<string>>(
    new Set(),
  );
  const [impact, setImpact] = React.useState<ImpactAnalysisResponse | null>(
    null,
  );
  const [impactBusy, setImpactBusy] = React.useState(false);
  const [impactError, setImpactError] = React.useState<string | null>(null);
  const [pendingEdge, setPendingEdge] = React.useState<{
    from: string;
    to: string;
  } | null>(null);

  // --------------------------------------------------------------------
  // AC-F2: 401 from GET tasks/dag → router.replace("/login"), never
  // render workspace-scoped UI. Page early-returns an aria-hidden shell.
  // --------------------------------------------------------------------
  React.useEffect(() => {
    if (error && error.status === 401) {
      router.replace("/login");
    }
  }, [error, router]);

  if (error && error.status === 401) {
    return (
      <div
        data-screen-id="S-029"
        data-feature-id="F-007"
        data-screen-name="task_dag_view"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const errorMessage =
    error && error.status !== 401 ? error.toUserMessage() : null;

  const nodes: TaskDagNode[] = data?.nodes ?? [];
  const edges: TaskDagEdge[] = data?.edges ?? [];
  const positioned = layoutNodes(nodes);
  const nodeIndex = new Map(positioned.map((p) => [p.id, p]));

  const toggleFeature = (featureId: string) => {
    setOpenFeatureIds((prev) => {
      const next = new Set(prev);
      if (next.has(featureId)) next.delete(featureId);
      else next.add(featureId);
      return next;
    });
  };

  const handleNodeClick = async (taskId: string) => {
    setImpact(null);
    setImpactError(null);
    setImpactBusy(true);
    try {
      const payload = await analyzeImpact({ changed_task_id: taskId });
      setImpact(payload);
    } catch (err) {
      if (err instanceof TaskDagApiError) {
        if (err.status === 401) {
          router.replace("/login");
          return;
        }
        setImpactError(err.toUserMessage());
      } else {
        setImpactError("通信に失敗しました");
      }
    } finally {
      setImpactBusy(false);
    }
  };

  // AC-F4: POST /dependencies — surface 4xx into the side panel.
  const handleAddDependency = async (from: string, to: string) => {
    setPendingEdge({ from, to });
    setImpactError(null);
    try {
      await addDependency({
        from_task_id: from,
        to_task_id: to,
        type: "blocks",
      });
      await reload();
    } catch (err) {
      if (err instanceof TaskDagApiError) {
        if (err.status === 401) {
          router.replace("/login");
          return;
        }
        setImpactError(err.toUserMessage());
      } else {
        setImpactError("通信に失敗しました");
      }
    } finally {
      setPendingEdge(null);
    }
  };

  const groups: TasksByFeatureGroup[] = byFeature?.groups ?? [];

  return (
    <div
      data-screen-id="S-029"
      data-feature-id="F-007"
      data-task-ids="T-V3-C-59,T-V3-RF-13,T-V3-FIX-03"
      data-entities="E-018,E-019"
      data-phase="Phase 1"
      data-screen-name="task_dag_view"
      className="min-h-screen bg-slate-50 text-slate-900 flex"
    >
      {/* Sidebar (matches mock S-029 left nav) */}
      <aside className="w-[240px] bg-eb-700 text-white flex flex-col shrink-0">
        <div className="px-5 py-4 border-b border-eb-600">
          <div className="text-[11px] tracking-widest text-eb-100 font-bold">
            BUILD-FACTORY
          </div>
          <div className="text-sm font-bold mt-1">Build-Factory dogfood</div>
        </div>
        <nav className="flex-1 px-2 py-3 text-sm space-y-0.5 overflow-y-auto">
          <a
            href="/dashboard"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <LayoutDashboard className="w-4 h-4" aria-hidden />
            ダッシュボード
          </a>
          <div className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold">
            Task
          </div>
          <a
            href="/task/kanban"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Kanban className="w-4 h-4" aria-hidden />
            Kanban
          </a>
          <a
            href="/task/list"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <List className="w-4 h-4" aria-hidden />
            List
          </a>
          <span
            aria-current="page"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold"
          >
            <GitBranch className="w-4 h-4" aria-hidden />
            DAG
          </span>
          <a
            href="/task/detail"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <FileText className="w-4 h-4" aria-hidden />
            Detail
          </a>
          <div className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold">
            Execution
          </div>
          <a
            href="/swarm"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Grid3x3 className="w-4 h-4" aria-hidden />
            Swarm Grid
          </a>
        </nav>
        <div className="px-4 py-3 border-t border-eb-600">
          <a
            href="/dashboard"
            className="text-[11px] text-eb-100 inline-flex items-center gap-1 hover:text-white"
          >
            <ArrowLeft className="w-3 h-3" aria-hidden />
            ダッシュボードへ戻る
          </a>
        </div>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-lg font-bold flex items-center gap-2">
              <GitBranch className="w-5 h-5 text-eb-500" aria-hidden />
              {S029_H1_TEXT}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">{S029_SUBTITLE}</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              data-testid="phase-filter"
              aria-label="Phase フィルタ"
              className="border border-slate-200 bg-white text-xs h-8 px-2 rounded-md"
              defaultValue="all"
            >
              <option value="all">全 Phase</option>
              <option value="phase-1">Phase 1</option>
            </select>
            <select
              data-testid="status-filter"
              aria-label="Status フィルタ"
              className="border border-slate-200 bg-white text-xs h-8 px-2 rounded-md"
              defaultValue="all"
            >
              <option value="all">全 Status</option>
              <option value="running">running</option>
              <option value="blocked">blocked</option>
            </select>
            <button
              type="button"
              data-testid="reload"
              onClick={() => void reload()}
              className="border border-slate-200 hover:bg-slate-50 text-xs h-8 px-3 rounded-md flex items-center gap-2"
            >
              <Workflow className="w-4 h-4" aria-hidden />
              再読み込み
            </button>
          </div>
        </div>

        {/* AC-F1 inline error toast (4xx surface, non-technical) */}
        {errorMessage && (
          <div
            role="alert"
            data-testid="task-dag-error"
            className="mx-6 mt-4 p-3 rounded-md bg-amber-50 border border-amber-300 text-amber-800 text-sm flex items-start gap-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
            <span>{errorMessage}</span>
          </div>
        )}

        <div className="flex-1 flex overflow-hidden">
          {/* Canvas */}
          <div
            className="flex-1 relative bg-slate-100 overflow-auto"
            style={{
              backgroundImage:
                "radial-gradient(circle, #cbd5e1 1px, transparent 1px)",
              backgroundSize: "16px 16px",
            }}
            data-testid="dag-canvas"
          >
            {loading && (
              <div
                className="absolute inset-0 flex items-center justify-center text-sm text-slate-500"
                role="status"
                aria-live="polite"
                data-testid="dag-loading"
              >
                読み込み中…
              </div>
            )}

            {!loading && (errorMessage || nodes.length === 0) && (
              <div
                className="absolute inset-0 flex items-center justify-center text-sm text-slate-500"
                data-testid="dag-empty"
              >
                {errorMessage
                  ? "タスク DAG を読み込めませんでした。"
                  : "まだタスク DAG が登録されていません。"}
              </div>
            )}

            {!loading && !errorMessage && nodes.length > 0 && (
              <svg
                data-testid="dag-svg"
                role="img"
                aria-label="タスク DAG"
                width={Math.max(1200, 60 + 6 * (140 + 80))}
                height={Math.max(
                  700,
                  90 + Math.ceil(positioned.length / 6) * (72 + 48),
                )}
                className="absolute"
              >
                <defs>
                  <marker
                    id="arrow-s029-default"
                    viewBox="0 0 10 10"
                    refX="9"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto"
                  >
                    <path d="M0,0 L10,5 L0,10 z" fill="#1a6648" />
                  </marker>
                  <marker
                    id="arrow-s029-block"
                    viewBox="0 0 10 10"
                    refX="9"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto"
                  >
                    <path d="M0,0 L10,5 L0,10 z" fill="#dc2626" />
                  </marker>
                  <marker
                    id="arrow-s029-soft"
                    viewBox="0 0 10 10"
                    refX="9"
                    refY="5"
                    markerWidth="6"
                    markerHeight="6"
                    orient="auto"
                  >
                    <path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" />
                  </marker>
                </defs>
                {edges.map((edge, idx) => {
                  const from = nodeIndex.get(edge.from_task_id);
                  const to = nodeIndex.get(edge.to_task_id);
                  if (!from || !to) return null;
                  const stroke = edgeStroke(edge.type);
                  const markerId =
                    edge.type === "blocks"
                      ? "arrow-s029-block"
                      : edge.type === "soft" || edge.type === "informs"
                        ? "arrow-s029-soft"
                        : "arrow-s029-default";
                  return (
                    <line
                      key={`${edge.from_task_id}->${edge.to_task_id}-${idx}`}
                      data-testid={`dag-edge-${edge.from_task_id}-${edge.to_task_id}`}
                      data-edge-type={edge.type ?? "blocks"}
                      x1={from.x + 140}
                      y1={from.y + 36}
                      x2={to.x}
                      y2={to.y + 36}
                      stroke={stroke}
                      strokeWidth={edge.type === "soft" ? 1.5 : 2}
                      strokeDasharray={
                        edge.type === "soft" || edge.type === "informs"
                          ? "4 4"
                          : undefined
                      }
                      markerEnd={`url(#${markerId})`}
                    />
                  );
                })}
              </svg>
            )}

            {!loading && !errorMessage && nodes.length > 0 && (
              <ul
                data-testid="dag-node-list"
                className="absolute inset-0 list-none"
              >
                {positioned.map((node) => (
                  <li
                    key={node.id}
                    className="absolute"
                    style={{
                      left: `${node.x}px`,
                      top: `${node.y}px`,
                      width: "140px",
                    }}
                  >
                    <button
                      type="button"
                      data-testid={`dag-node-${node.id}`}
                      data-task-status={node.status ?? "todo"}
                      onClick={() => void handleNodeClick(node.id)}
                      className={`block w-full text-left bg-white ${statusBorder(
                        node.status,
                      )} hover:border-eb-500 rounded-lg p-3 shadow-sm`}
                    >
                      <div className="text-[10px] mono text-eb-500 font-bold truncate">
                        {node.id}
                      </div>
                      <div className="text-xs font-semibold mt-0.5 truncate">
                        {node.title ?? node.id}
                      </div>
                      <div className="mt-1.5">
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full ${statusPill(
                            node.status,
                          )}`}
                        >
                          {node.status ?? "todo"}
                        </span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {/* Legend */}
            <div
              className="absolute bottom-4 left-4 bg-white border border-slate-200 rounded-md p-3 text-xs space-y-1.5"
              data-testid="dag-legend"
            >
              <div className="font-bold text-slate-700 mb-2">Status colors</div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded border-2 border-emerald-500"></div>
                done
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded border-2 border-amber-300 ring-1 ring-amber-100"></div>
                running
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded border border-slate-300"></div>
                todo
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded border-2 border-red-300 ring-1 ring-red-100"></div>
                blocked
              </div>
            </div>

            {/* Zoom controls (Lucide icons, mock parity) */}
            <div className="absolute top-4 right-4 bg-white border border-slate-200 rounded-md flex flex-col">
              <button
                type="button"
                aria-label="Zoom in"
                className="w-9 h-9 hover:bg-slate-50 border-b border-slate-200 flex items-center justify-center"
              >
                <Plus className="w-4 h-4" aria-hidden />
              </button>
              <button
                type="button"
                aria-label="Zoom out"
                className="w-9 h-9 hover:bg-slate-50 border-b border-slate-200 flex items-center justify-center"
              >
                <Minus className="w-4 h-4" aria-hidden />
              </button>
              <button
                type="button"
                aria-label="Fit view"
                className="w-9 h-9 hover:bg-slate-50 flex items-center justify-center"
              >
                <Maximize className="w-4 h-4" aria-hidden />
              </button>
            </div>
          </div>

          {/* Side panel: feature accordion (AC-F3) + impact analysis (AC-F4) */}
          <aside
            className="w-[320px] border-l border-slate-200 bg-white overflow-y-auto"
            data-testid="dag-side-panel"
          >
            <div className="px-4 py-3 border-b border-slate-200">
              <div className="text-xs font-bold text-slate-700">機能別タスク</div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                feature_id でグループ化
              </div>
            </div>
            <div
              data-testid="feature-accordion"
              className="px-2 py-2 space-y-1"
            >
              {groups.length === 0 && !loading && (
                <div
                  data-testid="feature-accordion-empty"
                  className="text-xs text-slate-500 px-3 py-2"
                >
                  グループ情報がまだありません。
                </div>
              )}
              {groups.map((group) => {
                const open = openFeatureIds.has(group.feature_id);
                const done = group.done_count ?? 0;
                const total = group.total_count ?? group.tasks.length;
                return (
                  <div
                    key={group.feature_id}
                    className="border border-slate-200 rounded-md"
                    data-testid={`feature-group-${group.feature_id}`}
                  >
                    <button
                      type="button"
                      onClick={() => toggleFeature(group.feature_id)}
                      aria-expanded={open}
                      data-testid={`feature-toggle-${group.feature_id}`}
                      className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-slate-50"
                    >
                      {open ? (
                        <ChevronDown className="w-4 h-4 text-slate-500" aria-hidden />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-slate-500" aria-hidden />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold truncate">
                          {group.feature_title ?? group.feature_id}
                        </div>
                        <div className="text-[10px] text-slate-500">
                          {group.feature_id}
                        </div>
                      </div>
                      <span className="text-[10px] bg-slate-100 text-slate-700 rounded-full px-2 py-0.5 mono">
                        {done} / {total}
                      </span>
                    </button>
                    {open && (
                      <ul
                        className="border-t border-slate-200 divide-y divide-slate-100"
                        data-testid={`feature-tasks-${group.feature_id}`}
                      >
                        {group.tasks.map((task) => (
                          <li
                            key={task.id}
                            className="px-3 py-2 text-xs flex items-center gap-2"
                          >
                            <span className="mono text-eb-500 text-[10px]">
                              {task.id}
                            </span>
                            <span className="flex-1 truncate">
                              {task.title ?? "(no title)"}
                            </span>
                            <span
                              className={`text-[10px] rounded-full px-1.5 py-0.5 ${statusPill(
                                task.status,
                              )}`}
                            >
                              {task.status ?? "todo"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="px-4 py-3 border-t border-slate-200 mt-2">
              <div className="text-xs font-bold text-slate-700">
                Impact analysis
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5">
                ノード選択で blast radius を表示
              </div>
            </div>
            <div className="px-4 py-3" data-testid="impact-panel">
              {impactBusy && (
                <div
                  role="status"
                  aria-live="polite"
                  data-testid="impact-loading"
                  className="text-xs text-slate-500"
                >
                  影響範囲を計算中…
                </div>
              )}
              {impactError && (
                <div
                  role="alert"
                  data-testid="impact-error"
                  className="text-xs text-amber-800 bg-amber-50 border border-amber-300 rounded-md p-2"
                >
                  {impactError}
                </div>
              )}
              {!impactBusy && !impactError && impact && (
                <div data-testid="impact-result">
                  <div className="text-xs text-slate-700 mb-1">
                    Blast radius:{" "}
                    <span className="mono font-bold">{impact.blast_radius}</span>
                  </div>
                  <ul className="space-y-1">
                    {impact.affected_tasks.map((t) => (
                      <li
                        key={t.id}
                        className="text-[11px] text-slate-700 flex items-center gap-2"
                        data-testid={`impact-affected-${t.id}`}
                      >
                        <span className="mono text-eb-500">{t.id}</span>
                        <span className="flex-1 truncate">
                          {t.title ?? "(no title)"}
                        </span>
                        <span
                          className={`text-[10px] rounded-full px-1.5 py-0.5 ${statusPill(
                            t.status ?? undefined,
                          )}`}
                        >
                          {t.status ?? "todo"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {!impactBusy && !impactError && !impact && (
                <div className="text-[11px] text-slate-500">
                  ノードをクリックすると影響範囲を表示します。
                </div>
              )}
            </div>

            {/* AC-F4: simple add-dependency form (mocks parity: hidden by default) */}
            <details
              className="mx-4 mb-4 mt-2 border border-slate-200 rounded-md"
              data-testid="add-dependency"
            >
              <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-slate-700">
                依存関係を追加
              </summary>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const from = (
                    form.elements.namedItem("from_task_id") as HTMLInputElement
                  )?.value;
                  const to = (
                    form.elements.namedItem("to_task_id") as HTMLInputElement
                  )?.value;
                  if (from && to)
                    void handleAddDependency(from, to);
                }}
                className="p-3 space-y-2"
              >
                <label className="block text-[11px] text-slate-600">
                  from task id
                  <input
                    name="from_task_id"
                    data-testid="dep-from"
                    className="block w-full border border-slate-200 rounded-md px-2 py-1 text-xs"
                    required
                  />
                </label>
                <label className="block text-[11px] text-slate-600">
                  to task id
                  <input
                    name="to_task_id"
                    data-testid="dep-to"
                    className="block w-full border border-slate-200 rounded-md px-2 py-1 text-xs"
                    required
                  />
                </label>
                <button
                  type="submit"
                  data-testid="dep-submit"
                  disabled={pendingEdge !== null}
                  className="w-full bg-eb-500 hover:bg-eb-600 text-white text-xs font-semibold rounded-md py-1.5 disabled:opacity-60"
                >
                  追加
                </button>
              </form>
            </details>
          </aside>
        </div>
      </main>
    </div>
  );
}
