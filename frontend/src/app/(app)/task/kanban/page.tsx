"use client";

/**
 * S-027 タスク Kanban — T-V3-C-57-1 / F-007.
 *
 * @screen-id S-027
 * @feature-id F-007
 * @task-ids T-V3-C-57-1,T-V3-RF-11
 * @entities E-018,E-019
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/task/S-027-task-kanban.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-57-1.md):
 *   structural.AC-S1 (h1 == "タスク Kanban" / mock h1 逐語)            — page heading.
 *   structural.AC-S2 (feature-grouped accordion × 4 columns, no flat 6) — AccordionBoard.
 *   structural.AC-S3 (default-expand only in-progress features)        — useKanbanBoard.
 *   structural.AC-S4 (Lucide icons exclusively / no emoji glyphs)      — see Lucide imports.
 *   functional.AC-F1 (EVENT-DRIVEN GET /api/workspaces/{id}/tasks?group_by=feature
 *     on mount; 2xx renders accordion view-model)                      — useKanbanBoard hook.
 *   functional.AC-F2 (UNWANTED: unauthenticated → redirect /login,
 *     never render workspace-scoped data)                              — useRouter().replace("/login").
 *   functional.AC-F3 (STATE-DRIVEN skeleton accordion with role="status"
 *     aria-live="polite" while data is loading)                        — see <KanbanSkeleton/>.
 *   functional.AC-F4 (UNWANTED: 403 → render 403 page instead of partial) — see <KanbanForbidden/>.
 *
 * Backend contract: T-V3-B-11 / T-V3-B-12 (already merged on earlier waves)
 * implemented backend/routers/workspaces.py::get_workspaces_by_id_tasks.
 *
 * Drag & drop and filter wiring are intentionally out of scope here (see
 * T-V3-C-57-2 / T-V3-C-57-3). This task only delivers the accordion layout,
 * the per-column rendering, and the GET data fetch.
 *
 * Workspace scoping: the page reads ?workspace_id from the search params; in
 * production the (app) layout will supply it from the active workspace. Until
 * that wiring lands we default to "active" (the backend already accepts the
 * sentinel via x-bf-implementation-path, mirroring T-V3-C-51).
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  Filter,
  Kanban,
  LayoutDashboard,
  Play,
  Search,
  ShieldOff,
} from "lucide-react";

import { KanbanApiError } from "@/api/kanban";
import { AccordionBoard } from "@/components/kanban/AccordionBoard";
import { useKanbanBoard } from "@/hooks/use-kanban-board";

// --------------------------------------------------------------------------
// Mock-derived literals — 逐語 from docs/mocks/2026-05-15_v3/task/S-027-*.html
// --------------------------------------------------------------------------

const S027_H1_TEXT = "タスク Kanban";
const S027_SUBTITLE =
  "機能別アコーディオン × 4 列 (Todo / In Progress / Review / Done)";

// --------------------------------------------------------------------------
// Loading skeleton (AC-F3 — STATE-DRIVEN role="status" aria-live="polite")
// --------------------------------------------------------------------------

function KanbanSkeleton(): React.ReactElement {
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="kanban-skeleton"
      className="p-4 space-y-3"
    >
      {[0, 1, 2].map((idx) => (
        <div
          key={idx}
          aria-hidden
          className="bg-white border border-slate-200 rounded-lg overflow-hidden"
        >
          <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center gap-3">
            <span className="w-4 h-4 rounded bg-slate-200 animate-pulse" />
            <span className="w-40 h-3 rounded bg-slate-200 animate-pulse" />
            <span className="ml-auto w-24 h-3 rounded bg-slate-200 animate-pulse" />
          </div>
          <div className="grid grid-cols-4 gap-3 p-3 bg-slate-50">
            {[0, 1, 2, 3].map((col) => (
              <div
                key={col}
                className="space-y-2"
              >
                <span className="block w-16 h-3 rounded bg-slate-200 animate-pulse" />
                <span className="block w-full h-12 rounded bg-slate-100 animate-pulse" />
              </div>
            ))}
          </div>
        </div>
      ))}
      <span className="sr-only">読み込み中…</span>
    </div>
  );
}

// --------------------------------------------------------------------------
// 403 inline forbidden state (AC-F4 — render S-046 instead of partial data)
// --------------------------------------------------------------------------

function KanbanForbidden(): React.ReactElement {
  return (
    <div
      role="alert"
      data-testid="kanban-forbidden"
      className="m-6 rounded-lg border border-rose-200 bg-rose-50 p-6 flex items-start gap-3"
    >
      <ShieldOff
        className="w-6 h-6 text-rose-600 mt-0.5 shrink-0"
        aria-hidden
      />
      <div>
        <h2 className="text-base font-bold text-rose-800">
          このワークスペースのタスクを閲覧する権限がありません
        </h2>
        <p className="text-sm text-rose-700 mt-1">
          管理者にワークスペースメンバー権限の付与を依頼してください。
        </p>
        <a
          href="/forbidden"
          className="text-sm font-semibold text-rose-700 underline mt-2 inline-block"
        >
          詳細を確認する (S-046)
        </a>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function TaskKanbanPage(): React.ReactElement {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams?.get("workspace_id") ?? "active";

  const { sections, loading, error } = useKanbanBoard(workspaceId);

  // AC-F2: 401 from GET /tasks → router.replace("/login"), never render
  // workspace-scoped UI. Page early-returns an aria-hidden shell.
  React.useEffect(() => {
    if (error && error.status === 401) {
      router.replace("/login");
    }
  }, [error, router]);

  if (error && error.status === 401) {
    return (
      <div
        data-screen-id="S-027"
        data-feature-id="F-007"
        data-screen-name="task_kanban"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const errorMessage =
    error && error.status !== 401 && error.status !== 403
      ? error.toUserMessage()
      : null;

  // Aggregate stats — drives the header status bar (mock parity L60-66).
  const totals = sections.reduce(
    (acc, s) => {
      acc.todo += s.columns.todo.length;
      acc.wip += s.columns.in_progress.length;
      acc.review += s.columns.review.length;
      acc.done += s.columns.done.length;
      acc.total += s.total;
      return acc;
    },
    { todo: 0, wip: 0, review: 0, done: 0, total: 0 },
  );
  const donePct =
    totals.total > 0 ? Math.round((totals.done / totals.total) * 100) : 0;

  return (
    <div
      data-screen-id="S-027"
      data-feature-id="F-007"
      data-task-ids="T-V3-C-57-1,T-V3-RF-11"
      data-entities="E-018,E-019"
      data-phase="Phase 1"
      data-screen-name="task_kanban"
      className="min-h-screen bg-slate-50 text-slate-900 flex"
    >
      {/* Sidebar (matches mock S-027 left nav) */}
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
          <span
            aria-current="page"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold"
          >
            <Kanban className="w-4 h-4" aria-hidden />
            Kanban
          </span>
        </nav>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="px-6 py-4 border-b border-slate-200 bg-white sticky top-0 z-10">
          <div className="flex items-end justify-between mb-3">
            <div>
              <h1 className="text-lg font-bold flex items-center gap-2">
                <Kanban className="w-5 h-5 text-eb-500" aria-hidden />
                {S027_H1_TEXT}
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">{S027_SUBTITLE}</p>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search
                  className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
                  aria-hidden
                />
                <input
                  type="search"
                  placeholder="task 検索..."
                  aria-label="task search (Wave 2 / T-V3-C-57-3 で実装)"
                  disabled
                  className="border border-slate-200 text-xs h-8 pl-7 pr-2 rounded-md w-48 disabled:bg-slate-50"
                />
              </div>
              <button
                type="button"
                disabled
                aria-label="filter (Wave 2 / T-V3-C-57-3 で実装)"
                className="border border-slate-200 hover:bg-slate-50 text-xs h-8 px-3 rounded-md flex items-center gap-1 disabled:bg-slate-50"
              >
                <Filter className="w-3 h-3" aria-hidden />
                filter
              </button>
              <button
                type="button"
                disabled
                aria-label="bulk play (Wave 2 / 別 task で実装)"
                className="bg-eb-500 hover:bg-eb-600 text-white text-xs h-8 px-3 rounded-md font-semibold flex items-center gap-1 disabled:bg-slate-300"
              >
                <Play className="w-3 h-3" aria-hidden />
                選択 task を Play (並列実行)
              </button>
            </div>
          </div>
          <div
            data-testid="kanban-stats"
            className="flex items-center gap-4 text-xs"
          >
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-slate-300" />
              <span className="text-slate-600">Todo</span>
              <span data-stat-todo className="font-bold mono">
                {totals.todo}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="text-slate-600">In Progress</span>
              <span data-stat-wip className="font-bold mono">
                {totals.wip}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-500" />
              <span className="text-slate-600">Review</span>
              <span data-stat-review className="font-bold mono">
                {totals.review}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-slate-600">Done</span>
              <span data-stat-done className="font-bold mono">
                {totals.done}
              </span>
            </div>
            <div className="ml-auto text-slate-500 mono text-[11px]">
              Total {totals.total} tasks · {totals.done}/{totals.total} (
              {donePct}%)
            </div>
          </div>
        </div>

        {errorMessage && (
          <div
            role="alert"
            data-testid="kanban-error"
            className="mx-6 mt-4 p-3 rounded-md bg-amber-50 border border-amber-300 text-amber-800 text-sm flex items-start gap-2"
          >
            <AlertTriangle
              className="w-4 h-4 mt-0.5 shrink-0"
              aria-hidden
            />
            <span>{errorMessage}</span>
          </div>
        )}

        {error && error.status === 403 ? (
          <KanbanForbidden />
        ) : loading ? (
          <KanbanSkeleton />
        ) : (
          <AccordionBoard sections={sections} />
        )}
      </main>
    </div>
  );
}

/** Re-export the error class for downstream consumers / tests. */
export { KanbanApiError };
