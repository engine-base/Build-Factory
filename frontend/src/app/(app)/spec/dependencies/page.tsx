"use client";

/**
 * S-017 依存グラフ (DAG) — T-V3-C-38 / F-009.
 *
 * @screen-id S-017
 * @feature-id F-009
 * @task-ids T-V3-C-38,T-V3-RF-07,T-V3-FIX-03
 * @entities E-019,E-018
 * @phase Phase 1 / Wave 1 / Group C
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/moat/S-017-dependency-graph.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-38.md):
 *   structural.AC-S1 (h1 == "依存グラフ (DAG)")                — page heading.
 *   structural.AC-S2 (Lucide icons exclusively / no emoji)      — see Lucide imports.
 *   functional.AC-F1 (GET /api/workspaces/{id}/dependencies typed client on
 *     mount — render 2xx into the page / 4xx -> inline error toast + empty state)
 *     — useEffect on mount.
 *   functional.AC-F2 (UNWANTED: unauthenticated -> redirect to /login (S-001) /
 *     never render workspace-scoped data) — useRouter().replace("/login") on 401.
 *   functional.AC-F3 (POST /api/workspaces/{id}/dependencies typed client on
 *     "依存追加" submit — server returns 200 with dependency_id) — handleAddDep.
 *
 * Workspace scoping: the page reads ?workspace_id from the search params; in
 * production the (app) layout will supply it from the active workspace. Until
 * that wiring lands we default to "active" (T-V3-B-009 already accepts the
 * sentinel via x-bf-implementation-path).
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertOctagon,
  AlertTriangle,
  ArrowLeft,
  ArrowRight as LucideArrowRight,
  GitBranch,
  Layers,
  LayoutDashboard,
  Maximize,
  Minus,
  Plus,
  Shield,
  Zap,
} from "lucide-react";

import {
  createDependency,
  dependenciesCreateEndpoint,
  dependenciesImpactAnalysisEndpoint,
  dependenciesListEndpoint,
  DependenciesApiError,
  getDependencies,
  runImpactAnalysis,
  type DependenciesListResponse,
  type DependencyImpactAnalysisResponse,
  type DependencyTaskNode,
  type TaskDependency,
} from "@/api/dependencies";

// --------------------------------------------------------------------------
// Form state
// --------------------------------------------------------------------------

type AddDepFormState = {
  from_task_id: string;
  to_task_id: string;
  kind: "hard" | "soft";
};

const INITIAL_ADD_DEP_FORM: AddDepFormState = {
  from_task_id: "",
  to_task_id: "",
  kind: "hard",
};

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function statusBadge(status: string | undefined | null): {
  label: string;
  className: string;
} {
  const s = String(status ?? "todo").toLowerCase();
  if (s === "done" || s === "completed") {
    return {
      label: "done",
      className: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    };
  }
  if (s === "running" || s === "in_progress") {
    return {
      label: "running",
      className: "bg-amber-50 text-amber-700 border border-amber-200",
    };
  }
  if (s === "blocked" || s === "blocked_question" || s === "blocked_dependency") {
    return {
      label: s,
      className: "bg-rose-50 text-rose-700 border border-rose-200",
    };
  }
  return {
    label: "todo",
    className: "bg-slate-100 text-slate-600",
  };
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function DependencyGraphPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams?.get("workspace_id") ?? "active";

  const [data, setData] = React.useState<DependenciesListResponse | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [phaseFilter, setPhaseFilter] = React.useState<string>("all");

  // "依存追加" dialog state (AC-F3 trigger).
  const [addOpen, setAddOpen] = React.useState(false);
  const [addForm, setAddForm] =
    React.useState<AddDepFormState>(INITIAL_ADD_DEP_FORM);
  const [addBusy, setAddBusy] = React.useState(false);

  // "影響範囲分析" dialog state.
  const [impactOpen, setImpactOpen] = React.useState(false);
  const [impactTaskId, setImpactTaskId] = React.useState("");
  const [impactBusy, setImpactBusy] = React.useState(false);
  const [impactResult, setImpactResult] =
    React.useState<DependencyImpactAnalysisResponse | null>(null);

  // ----------------------------------------------------------------------
  // AC-F1 / AC-F2: error surface helper. 401 always routes to /login (S-001)
  // without rendering workspace-scoped data first.
  // ----------------------------------------------------------------------
  const surfaceError = React.useCallback(
    (err: unknown, fallbackEndpoint: string) => {
      if (err instanceof DependenciesApiError && err.status === 401) {
        // AC-F2 (UNWANTED): unauthenticated -> /login, drop any workspace data.
        setData(null);
        setErrorMessage(null);
        router.replace("/login");
        return;
      }
      const msg =
        err instanceof DependenciesApiError
          ? err.toUserMessage()
          : `通信に失敗しました (${fallbackEndpoint})`;
      setErrorMessage(msg);
    },
    [router],
  );

  // ----------------------------------------------------------------------
  // AC-F1: GET /api/workspaces/{id}/dependencies on mount.
  // ----------------------------------------------------------------------
  const loadDependencies = React.useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const payload = await getDependencies(workspaceId);
      setData(payload);
    } catch (err) {
      surfaceError(err, dependenciesListEndpoint(workspaceId));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, surfaceError]);

  React.useEffect(() => {
    void loadDependencies();
  }, [loadDependencies]);

  // ----------------------------------------------------------------------
  // AC-F3: POST /api/workspaces/{id}/dependencies (依存追加 form).
  // ----------------------------------------------------------------------
  const handleAddDep = React.useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (addBusy) return;
      if (!addForm.from_task_id.trim() || !addForm.to_task_id.trim()) return;
      setAddBusy(true);
      setErrorMessage(null);
      try {
        await createDependency(workspaceId, {
          from_task_id: addForm.from_task_id.trim(),
          to_task_id: addForm.to_task_id.trim(),
          kind: addForm.kind,
        });
        setAddOpen(false);
        setAddForm(INITIAL_ADD_DEP_FORM);
        await loadDependencies();
      } catch (err) {
        surfaceError(err, dependenciesCreateEndpoint(workspaceId));
      } finally {
        setAddBusy(false);
      }
    },
    [addBusy, addForm, workspaceId, loadDependencies, surfaceError],
  );

  // ----------------------------------------------------------------------
  // 影響範囲分析: POST /api/workspaces/{id}/dependencies/impact-analysis.
  // ----------------------------------------------------------------------
  const handleImpactAnalysis = React.useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (impactBusy) return;
      if (!impactTaskId.trim()) return;
      setImpactBusy(true);
      setErrorMessage(null);
      try {
        const result = await runImpactAnalysis(workspaceId, {
          changed_task_id: impactTaskId.trim(),
        });
        setImpactResult(result);
      } catch (err) {
        surfaceError(err, dependenciesImpactAnalysisEndpoint(workspaceId));
        setImpactResult(null);
      } finally {
        setImpactBusy(false);
      }
    },
    [
      impactBusy,
      impactTaskId,
      workspaceId,
      surfaceError,
    ],
  );

  // ----------------------------------------------------------------------
  // Derived: visible edges + node id set for SVG rendering.
  // ----------------------------------------------------------------------
  const dependencies: TaskDependency[] = React.useMemo(
    () => data?.dependencies ?? [],
    [data],
  );
  const tasks: DependencyTaskNode[] = React.useMemo(
    () => data?.tasks ?? [],
    [data],
  );

  const filteredTasks = React.useMemo(() => {
    if (phaseFilter === "all") return tasks;
    return tasks.filter((t) => (t.phase ?? "").toLowerCase() === phaseFilter.toLowerCase());
  }, [tasks, phaseFilter]);

  const visibleTaskIds = React.useMemo(
    () => new Set(filteredTasks.map((t) => t.id)),
    [filteredTasks],
  );

  return (
    <div
      data-screen-id="S-017"
      data-feature-id="F-009"
      data-task-ids="T-V3-C-38,T-V3-RF-07,T-V3-FIX-03"
      data-entities="E-019,E-018"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900 flex"
    >
      {/* Sidebar (matches mock S-017 left nav) */}
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
          <a
            href="/spec/phases"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Layers className="w-4 h-4" aria-hidden />
            フェーズ管理
          </a>
          <span
            aria-current="page"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold"
          >
            <GitBranch className="w-4 h-4" aria-hidden />
            依存グラフ
          </span>
          <div className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold">
            Moat / Safety
          </div>
          <a
            href="/spec/constitution"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Shield className="w-4 h-4" aria-hidden />
            Constitution
          </a>
          <a
            href="/spec/red-lines"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <AlertOctagon className="w-4 h-4" aria-hidden />
            赤線設定
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

      <main className="flex-1 flex flex-col">
        <div className="px-6 py-4 border-b border-slate-200 bg-white flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold flex items-center gap-2">
              <GitBranch className="w-5 h-5 text-eb-500" aria-hidden />
              依存グラフ (DAG)
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              タスク・機能の依存関係を React Flow で可視化
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              data-testid="phase-filter"
              aria-label="Phase フィルタ"
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md"
              value={phaseFilter}
              onChange={(e) => setPhaseFilter(e.target.value)}
            >
              <option value="all">全 Phase</option>
              <option value="Phase 1">Phase 1</option>
              <option value="Phase 2">Phase 2</option>
            </select>
            <button
              type="button"
              data-testid="impact-analysis-open"
              onClick={() => {
                setImpactOpen(true);
                setImpactResult(null);
              }}
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2"
            >
              <Zap className="w-4 h-4" aria-hidden />
              影響範囲分析
            </button>
            <button
              type="button"
              data-testid="add-dep-open"
              onClick={() => setAddOpen(true)}
              className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2"
            >
              <Plus className="w-4 h-4" aria-hidden />
              依存追加
            </button>
          </div>
        </div>

        {/* AC-F1 inline error toast (4xx surface, non-technical) */}
        {errorMessage && (
          <div
            role="alert"
            data-testid="dependency-graph-error"
            className="mx-6 mt-4 p-3 rounded-md bg-amber-50 border border-amber-300 text-amber-800 text-sm flex items-start gap-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* DAG canvas */}
        <div
          className="flex-1 relative bg-slate-100 overflow-hidden"
          style={{
            backgroundImage:
              "radial-gradient(circle, #cbd5e1 1px, transparent 1px)",
            backgroundSize: "16px 16px",
          }}
          data-testid="dag-canvas"
        >
          {loading && !data && (
            <div
              className="absolute inset-0 flex items-center justify-center text-sm text-slate-500"
              data-testid="dag-loading"
            >
              読み込み中…
            </div>
          )}

          {!loading && (errorMessage || dependencies.length === 0) && (
            <div
              className="absolute inset-0 flex items-center justify-center text-sm text-slate-500"
              data-testid="dag-empty"
            >
              {errorMessage
                ? "依存関係を読み込めませんでした。"
                : "まだ依存関係が登録されていません。"}
            </div>
          )}

          {!loading && !errorMessage && dependencies.length > 0 && (
            <ul
              data-testid="dependency-list"
              className="absolute top-4 left-4 right-4 bottom-4 overflow-auto bg-white/80 backdrop-blur rounded-lg border border-slate-200 divide-y divide-slate-100"
            >
              {dependencies
                .filter(
                  (dep) =>
                    visibleTaskIds.size === 0 ||
                    visibleTaskIds.has(dep.from_task_id) ||
                    visibleTaskIds.has(dep.to_task_id),
                )
                .map((dep) => {
                  const fromTask = tasks.find((t) => t.id === dep.from_task_id);
                  const toTask = tasks.find((t) => t.id === dep.to_task_id);
                  const fromBadge = statusBadge(fromTask?.status);
                  const toBadge = statusBadge(toTask?.status);
                  return (
                    <li
                      key={dep.id}
                      data-testid={`dependency-row-${dep.id}`}
                      className="flex items-center gap-3 px-4 py-3 text-sm"
                    >
                      <span className="mono text-[11px] text-slate-500 w-40 truncate">
                        {dep.from_task_id}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded-full ${fromBadge.className}`}
                      >
                        {fromBadge.label}
                      </span>
                      <ArrowRight />
                      <span className="mono text-[11px] text-slate-500 w-40 truncate">
                        {dep.to_task_id}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded-full ${toBadge.className}`}
                      >
                        {toBadge.label}
                      </span>
                      <span className="ml-auto text-[10px] text-slate-500 uppercase mono">
                        {dep.kind ?? "hard"}
                      </span>
                    </li>
                  );
                })}
            </ul>
          )}

          {/* Canvas controls (Lucide icons, mock parity) */}
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
      </main>

      {/* AC-F3 dialog: "依存追加" */}
      {addOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-dep-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40"
          onClick={() => !addBusy && setAddOpen(false)}
        >
          <form
            onSubmit={handleAddDep}
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-lg shadow-xl w-[420px] p-5 space-y-3"
            data-testid="add-dep-form"
          >
            <h2 id="add-dep-title" className="text-base font-bold">
              依存追加
            </h2>
            <p className="text-xs text-slate-600">
              from_task が完了するまで to_task は開始できません。循環は 409
              でブロックされます。
            </p>
            <div className="space-y-1.5">
              <label htmlFor="dep-from" className="text-xs font-medium block">
                from_task_id (先行)
              </label>
              <input
                id="dep-from"
                type="text"
                value={addForm.from_task_id}
                onChange={(e) =>
                  setAddForm({ ...addForm, from_task_id: e.target.value })
                }
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm mono"
                required
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="dep-to" className="text-xs font-medium block">
                to_task_id (後続)
              </label>
              <input
                id="dep-to"
                type="text"
                value={addForm.to_task_id}
                onChange={(e) =>
                  setAddForm({ ...addForm, to_task_id: e.target.value })
                }
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm mono"
                required
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="dep-kind" className="text-xs font-medium block">
                種別
              </label>
              <select
                id="dep-kind"
                value={addForm.kind}
                onChange={(e) =>
                  setAddForm({
                    ...addForm,
                    kind: e.target.value === "soft" ? "soft" : "hard",
                  })
                }
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm"
              >
                <option value="hard">hard (blocking)</option>
                <option value="soft">soft (informational)</option>
              </select>
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setAddOpen(false)}
                disabled={addBusy}
                className="text-sm h-9 px-3 rounded-md border border-slate-200 hover:bg-slate-50"
              >
                キャンセル
              </button>
              <button
                type="submit"
                data-testid="add-dep-submit"
                disabled={addBusy}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm h-9 px-4 rounded-md font-semibold"
              >
                {addBusy ? "追加中…" : "依存を追加"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 影響範囲分析 dialog */}
      {impactOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="impact-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40"
          onClick={() => !impactBusy && setImpactOpen(false)}
        >
          <form
            onSubmit={handleImpactAnalysis}
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-lg shadow-xl w-[460px] p-5 space-y-3"
            data-testid="impact-form"
          >
            <h2 id="impact-title" className="text-base font-bold">
              影響範囲分析
            </h2>
            <p className="text-xs text-slate-600">
              指定したタスクを変更した場合に下流に伝搬する task を列挙します。
            </p>
            <div className="space-y-1.5">
              <label htmlFor="impact-task" className="text-xs font-medium block">
                変更対象 task_id
              </label>
              <input
                id="impact-task"
                type="text"
                value={impactTaskId}
                onChange={(e) => setImpactTaskId(e.target.value)}
                className="w-full h-9 px-2 border border-slate-300 rounded-md text-sm mono"
                required
              />
            </div>

            {impactResult && (
              <div
                data-testid="impact-result"
                className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs"
              >
                <div className="font-bold mb-1.5">
                  影響範囲: {impactResult.blast_radius} task
                  {impactResult.affected_tasks.length > 0 && " (下流タスク)"}
                </div>
                <ul className="space-y-0.5 max-h-32 overflow-auto">
                  {impactResult.affected_tasks.map((t) => (
                    <li key={t.id} className="mono text-slate-700">
                      {t.id} — {t.title}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setImpactOpen(false)}
                disabled={impactBusy}
                className="text-sm h-9 px-3 rounded-md border border-slate-200 hover:bg-slate-50"
              >
                閉じる
              </button>
              <button
                type="submit"
                data-testid="impact-submit"
                disabled={impactBusy}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm h-9 px-4 rounded-md font-semibold"
              >
                {impactBusy ? "分析中…" : "影響範囲を計算"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function ArrowRight() {
  // Lucide ArrowRight wrapped — no emoji / no HTML entity glyph.
  return (
    <LucideArrowRight
      aria-hidden
      className="w-3.5 h-3.5 text-slate-400 shrink-0"
    />
  );
}
