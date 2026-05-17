"use client";

/**
 * T-V3-C-58 / S-028: タスクリスト page (Vertical Slice / UI).
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/task/S-028-task-list.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-028
 * @feature-id F-007
 * @task-ids T-V3-C-58
 * @entities E-018
 * @phase Phase 1
 *
 * Backend contracts (T-V3-B-11 / F-007):
 *   GET  /api/workspaces/{id}/tasks
 *   POST /api/workspaces/{id}/tasks/bulk-play
 *   POST /api/workspaces/{id}/tasks/bulk-archive
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-58.md):
 *   structural.AC-S1 — h1 === "タスクリスト" (mock h1 逐語コピー).
 *   structural.AC-S2 — Lucide icons only (no emoji glyphs).
 *   functional.AC-F1 — GET /api/workspaces/{id}/tasks on mount; 2xx renders,
 *                      4xx → inline toast + empty state.
 *   functional.AC-F2 — 401 → router.replace("/login") (no workspace data render).
 *   functional.AC-F3 — GET /api/workspaces/{id}/tasks?group_by=feature returns
 *                      tasks grouped by feature_id with accordion-friendly metadata.
 *
 * Auth: workspace member required for GET / bulk-play; workspace_admin enforced
 * server-side for bulk-archive. The page surfaces 403 as a friendly toast tagged
 * with the failing endpoint.
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  Archive,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Download,
  List,
  Loader2,
  MoreVertical,
  Play,
  Search,
  XCircle,
} from "lucide-react";

import {
  TaskListApiError,
  type TaskGroup,
  type TaskGroupBy,
  type TaskListItem,
} from "@/api/task-list";
import { useTaskList } from "@/hooks/useTaskList";

// ---------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー (h1_text from screens.json[S-028]).
// AC-S1: h1_text === "タスクリスト"
// ---------------------------------------------------------------------------
const S028_H1_TEXT = "タスクリスト";

type SortKey = "task_id" | "title" | "feature_id" | "status" | "updated_at";
type SortDir = "asc" | "desc";

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  done: {
    label: "done",
    className: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  },
  completed: {
    label: "done",
    className: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  },
  running: {
    label: "running",
    className: "bg-amber-50 text-amber-700 border border-amber-200",
  },
  in_progress: {
    label: "running",
    className: "bg-amber-50 text-amber-700 border border-amber-200",
  },
  review: {
    label: "review",
    className: "bg-blue-50 text-blue-700 border border-blue-200",
  },
  review_needed: {
    label: "review",
    className: "bg-blue-50 text-blue-700 border border-blue-200",
  },
  todo: {
    label: "todo",
    className: "bg-slate-100 text-slate-600",
  },
  pending: {
    label: "todo",
    className: "bg-slate-100 text-slate-600",
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseWorkspaceId(value: string | null | undefined): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function compareValues(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
  dir: SortDir,
): number {
  const av = a ?? "";
  const bv = b ?? "";
  if (av < bv) return dir === "asc" ? -1 : 1;
  if (av > bv) return dir === "asc" ? 1 : -1;
  return 0;
}

function sortTasks(
  tasks: TaskListItem[],
  sortKey: SortKey,
  sortDir: SortDir,
): TaskListItem[] {
  return [...tasks].sort((a, b) => {
    const av = (a as Record<string, unknown>)[sortKey] as
      | string
      | number
      | null
      | undefined;
    const bv = (b as Record<string, unknown>)[sortKey] as
      | string
      | number
      | null
      | undefined;
    return compareValues(av, bv, sortDir);
  });
}

function filterTasks(
  tasks: TaskListItem[],
  filterText: string,
): TaskListItem[] {
  if (!filterText.trim()) return tasks;
  const q = filterText.trim().toLowerCase();
  return tasks.filter((t) => {
    const fields = [
      t.task_id,
      t.title,
      t.feature_id,
      t.status,
      t.assignee_name,
      t.assignee,
    ];
    return fields.some(
      (f) => typeof f === "string" && f.toLowerCase().includes(q),
    );
  });
}

function statusBadge(status: string | null | undefined): {
  label: string;
  className: string;
} {
  if (!status)
    return { label: "—", className: "bg-slate-100 text-slate-500" };
  return (
    STATUS_BADGE[status] ?? {
      label: status,
      className: "bg-slate-100 text-slate-700",
    }
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TaskListPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // workspace id is supplied via ?workspace=<id> for now; future routes may
  // embed it in the URL path. Falls back to 1 (Build-Factory dogfood).
  const workspaceIdRaw =
    parseWorkspaceId(searchParams?.get("workspace")) ?? 1;
  const groupByParam =
    (searchParams?.get("group_by") as TaskGroupBy | null) ?? "feature";

  const [sortKey, setSortKey] = React.useState<SortKey>("task_id");
  const [sortDir, setSortDir] = React.useState<SortDir>("asc");
  const [filterText, setFilterText] = React.useState("");
  const [selected, setSelected] = React.useState<Set<string>>(new Set());

  const {
    data,
    isPending,
    isError,
    isSuccess,
    error,
    refetch,
    bulkPlay,
    bulkArchive,
    isBulkPlaying,
    isBulkArchiving,
  } = useTaskList({
    workspaceId: workspaceIdRaw,
    groupBy: groupByParam,
  });

  // AC-F2: 401 → router.replace("/login") (no workspace data render).
  const redirectedRef = React.useRef(false);
  React.useEffect(() => {
    if (!isError) return;
    if (redirectedRef.current) return;
    if (error instanceof TaskListApiError && error.status === 401) {
      redirectedRef.current = true;
      router.replace("/login");
    }
  }, [isError, error, router]);

  // AC-F1 tail: on 4xx (non-401) surface a friendly toast tagged with the
  // failing endpoint and render an empty state below.
  const lastToastRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!isError) {
      lastToastRef.current = null;
      return;
    }
    if (error instanceof TaskListApiError && error.status === 401) {
      // The redirect effect handles 401; do not double-toast.
      return;
    }
    const userMsg =
      error instanceof TaskListApiError
        ? error.toUserMessage()
        : "タスクの読み込みに失敗しました";
    if (lastToastRef.current !== userMsg) {
      toast.error(userMsg);
      lastToastRef.current = userMsg;
    }
  }, [isError, error]);

  const tasks: TaskListItem[] = React.useMemo(
    () => data?.tasks ?? [],
    [data?.tasks],
  );
  const groups: TaskGroup[] = React.useMemo(
    () => data?.groups ?? [],
    [data?.groups],
  );

  const visibleTasks = React.useMemo(() => {
    const filtered = filterTasks(tasks, filterText);
    return sortTasks(filtered, sortKey, sortDir);
  }, [tasks, filterText, sortKey, sortDir]);

  const selectedTaskIds = React.useMemo(
    () =>
      visibleTasks
        .filter((t) => selected.has(String(t.id)))
        .map((t) => t.id),
    [visibleTasks, selected],
  );
  const selectionCount = selectedTaskIds.length;

  const toggleSelect = React.useCallback((id: number | string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      const key = String(id);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const toggleSelectAll = React.useCallback(() => {
    setSelected((prev) => {
      const allKeys = visibleTasks.map((t) => String(t.id));
      const allSelected =
        allKeys.length > 0 && allKeys.every((k) => prev.has(k));
      return allSelected ? new Set() : new Set(allKeys);
    });
  }, [visibleTasks]);

  const clearSelection = React.useCallback(() => {
    setSelected(new Set());
  }, []);

  const onSort = React.useCallback((key: SortKey) => {
    setSortKey((prevKey) => {
      if (prevKey === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return prevKey;
      }
      setSortDir("asc");
      return key;
    });
  }, []);

  const onBulkPlay = React.useCallback(async () => {
    if (!selectionCount || isBulkPlaying) return;
    try {
      const res = await bulkPlay({ task_ids: selectedTaskIds });
      toast.success(
        res?.queued
          ? `${res.queued} 件のセッションをキューに入れました`
          : `${selectionCount} 件のタスクを Play しました`,
      );
      clearSelection();
    } catch (err) {
      const userMsg =
        err instanceof TaskListApiError
          ? err.toUserMessage()
          : "一括 Play に失敗しました";
      toast.error(userMsg);
    }
  }, [
    selectionCount,
    selectedTaskIds,
    bulkPlay,
    isBulkPlaying,
    clearSelection,
  ]);

  const onBulkArchive = React.useCallback(async () => {
    if (!selectionCount || isBulkArchiving) return;
    try {
      const res = await bulkArchive({ task_ids: selectedTaskIds });
      toast.success(
        res?.archived_count !== undefined
          ? `${res.archived_count} 件のタスクをアーカイブしました`
          : `${selectionCount} 件のタスクをアーカイブしました`,
      );
      clearSelection();
    } catch (err) {
      const userMsg =
        err instanceof TaskListApiError
          ? err.toUserMessage()
          : "一括アーカイブに失敗しました";
      toast.error(userMsg);
    }
  }, [
    selectionCount,
    selectedTaskIds,
    bulkArchive,
    isBulkArchiving,
    clearSelection,
  ]);

  // 401 redirect terminal state — render nothing (AC-F2 "no workspace data").
  const isUnauthenticated =
    error instanceof TaskListApiError && error.status === 401;

  const headerCheckboxChecked =
    visibleTasks.length > 0 &&
    visibleTasks.every((t) => selected.has(String(t.id)));

  const sortIcon = (key: SortKey) => {
    if (sortKey !== key)
      return <ArrowUpDown className="w-3 h-3 inline" aria-hidden />;
    return sortDir === "asc" ? (
      <ArrowUp className="w-3 h-3 inline" aria-hidden />
    ) : (
      <ArrowDown className="w-3 h-3 inline" aria-hidden />
    );
  };

  return (
    <main
      data-screen-id="S-028"
      data-screen-name="task_list"
      data-feature-id="F-007"
      data-task-ids="T-V3-C-58"
      data-entities="E-018"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      {!isUnauthenticated && (
        <>
          <header className="px-6 py-4 border-b border-slate-200 bg-white">
            <div className="flex items-end justify-between mb-1 gap-3 flex-wrap">
              <div>
                <h1 className="text-lg font-bold flex items-center gap-2">
                  <List
                    className="w-5 h-5 text-eb-500"
                    aria-hidden
                  />
                  {S028_H1_TEXT}
                </h1>
                <p className="text-xs text-slate-500 mt-0.5">
                  高密度テーブル表示 / ソート + 一括操作 + CSV export
                </p>
              </div>
              <div className="flex items-center gap-2">
                <label htmlFor="task-search" className="sr-only">
                  タスク検索
                </label>
                <div className="relative">
                  <Search
                    className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
                    aria-hidden
                  />
                  <input
                    id="task-search"
                    data-testid="task-list-search"
                    type="search"
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                    placeholder="task 検索..."
                    className="border border-slate-200 text-xs h-8 pl-7 pr-2 rounded-md w-48"
                  />
                </div>
                <button
                  type="button"
                  data-testid="task-list-export"
                  className="border border-slate-200 hover:bg-slate-50 text-xs h-8 px-3 rounded-md flex items-center gap-1"
                >
                  <Download className="w-3 h-3" aria-hidden />
                  CSV export
                </button>
              </div>
            </div>
          </header>

          {/* AC-F3: accordion-friendly groups bar (visible when group_by=feature returns groups) */}
          {isSuccess && groups.length > 0 && (
            <div
              data-testid="task-list-groups"
              className="px-6 py-2 bg-white border-b border-slate-100 flex items-center gap-2 text-xs overflow-x-auto"
            >
              <span className="text-slate-500 font-semibold">
                Feature:
              </span>
              {groups.map((g) => (
                <span
                  key={g.key}
                  className="bg-slate-100 text-slate-700 mono px-2 py-0.5 rounded whitespace-nowrap"
                >
                  {g.label ?? g.key}
                  {typeof g.count === "number" && ` (${g.count})`}
                </span>
              ))}
            </div>
          )}

          {/* Bulk action bar (visible when rows selected) */}
          {selectionCount > 0 && (
            <div
              data-testid="task-list-bulk-bar"
              className="px-6 py-2 bg-eb-50 border-b border-eb-200 flex items-center gap-3"
            >
              <span className="text-xs font-medium text-eb-700">
                {selectionCount} 件選択中
              </span>
              <button
                type="button"
                data-testid="task-list-bulk-play"
                onClick={onBulkPlay}
                disabled={isBulkPlaying}
                className="text-xs bg-eb-500 hover:bg-eb-600 disabled:opacity-50 text-white px-3 py-1 rounded-md font-semibold flex items-center gap-1"
              >
                <Play className="w-3 h-3" aria-hidden />
                {isBulkPlaying ? "Play 中..." : "一括 Play"}
              </button>
              <button
                type="button"
                data-testid="task-list-bulk-archive"
                onClick={onBulkArchive}
                disabled={isBulkArchiving}
                className="text-xs border border-slate-300 hover:bg-white disabled:opacity-50 px-3 py-1 rounded-md flex items-center gap-1"
              >
                <Archive className="w-3 h-3" aria-hidden />
                {isBulkArchiving ? "アーカイブ中..." : "一括 Archive"}
              </button>
              <button
                type="button"
                onClick={clearSelection}
                className="text-xs text-slate-500 hover:text-slate-900"
              >
                選択解除
              </button>
            </div>
          )}

          {isPending && (
            <div
              data-testid="task-list-loading"
              role="status"
              aria-live="polite"
              className="flex items-center justify-center py-16 text-slate-500 gap-2 bg-white border-t border-slate-200"
            >
              <Loader2
                className="w-5 h-5 animate-spin text-eb-500"
                aria-hidden
              />
              <span className="text-sm">タスクを読み込み中...</span>
            </div>
          )}

          {isError && !isUnauthenticated && (
            <div
              data-testid="task-list-error-empty-state"
              role="alert"
              className="bg-white border-t border-amber-200 p-6"
            >
              <div className="flex items-start gap-3">
                <XCircle
                  className="w-5 h-5 text-amber-600 shrink-0"
                  aria-hidden
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold mb-1">
                    タスクを表示できません
                  </p>
                  <p className="text-xs text-slate-600">
                    {error instanceof TaskListApiError
                      ? error.toUserMessage()
                      : "サーバーで一時的なエラーが発生しました"}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      void refetch();
                    }}
                    className="mt-3 text-xs text-eb-500 hover:text-eb-600 font-semibold"
                  >
                    再試行
                  </button>
                </div>
              </div>
            </div>
          )}

          {isSuccess && visibleTasks.length === 0 && (
            <div
              data-testid="task-list-empty"
              className="bg-white border-t border-slate-200 p-12 text-center text-sm text-slate-500"
            >
              {filterText
                ? "条件に一致するタスクはありません"
                : "タスクはまだありません"}
            </div>
          )}

          {isSuccess && visibleTasks.length > 0 && (
            <div className="bg-white border-t border-slate-200">
              <table
                data-testid="task-list-table"
                className="w-full text-sm"
              >
                <thead className="bg-slate-50 sticky top-0">
                  <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                    <th className="px-3 py-2 text-left w-8">
                      <label className="sr-only" htmlFor="task-list-select-all">
                        すべて選択
                      </label>
                      <input
                        id="task-list-select-all"
                        data-testid="task-list-select-all"
                        type="checkbox"
                        checked={headerCheckboxChecked}
                        onChange={toggleSelectAll}
                        className="w-3.5 h-3.5 accent-eb-500"
                      />
                    </th>
                    <th
                      data-testid="task-list-sort-id"
                      className="px-3 py-2 text-left cursor-pointer hover:bg-slate-100"
                      onClick={() => onSort("task_id")}
                    >
                      ID {sortIcon("task_id")}
                    </th>
                    <th
                      data-testid="task-list-sort-title"
                      className="px-3 py-2 text-left cursor-pointer hover:bg-slate-100"
                      onClick={() => onSort("title")}
                    >
                      タイトル {sortIcon("title")}
                    </th>
                    <th
                      data-testid="task-list-sort-feature"
                      className="px-3 py-2 text-left cursor-pointer hover:bg-slate-100"
                      onClick={() => onSort("feature_id")}
                    >
                      Feature {sortIcon("feature_id")}
                    </th>
                    <th
                      data-testid="task-list-sort-status"
                      className="px-3 py-2 text-left cursor-pointer hover:bg-slate-100"
                      onClick={() => onSort("status")}
                    >
                      Status {sortIcon("status")}
                    </th>
                    <th className="px-3 py-2 text-left">担当</th>
                    <th className="px-3 py-2 text-right">工数</th>
                    <th className="px-3 py-2 text-right">cost</th>
                    <th
                      data-testid="task-list-sort-updated"
                      className="px-3 py-2 text-left cursor-pointer hover:bg-slate-100"
                      onClick={() => onSort("updated_at")}
                    >
                      更新 {sortIcon("updated_at")}
                    </th>
                    <th className="px-3 py-2 text-right w-8" aria-label="操作" />
                  </tr>
                </thead>
                <tbody>
                  {visibleTasks.map((t) => {
                    const isRowSelected = selected.has(String(t.id));
                    const badge = statusBadge(t.status);
                    return (
                      <tr
                        key={String(t.id)}
                        data-testid={`task-list-row-${t.id}`}
                        className={`border-t border-slate-100 hover:bg-slate-50 ${
                          isRowSelected ? "bg-eb-50/40" : ""
                        }`}
                      >
                        <td className="px-3 py-2">
                          <label
                            className="sr-only"
                            htmlFor={`task-list-row-checkbox-${t.id}`}
                          >
                            {String(t.task_id ?? t.id)} を選択
                          </label>
                          <input
                            id={`task-list-row-checkbox-${t.id}`}
                            data-testid={`task-list-row-checkbox-${t.id}`}
                            type="checkbox"
                            checked={isRowSelected}
                            onChange={() => toggleSelect(t.id)}
                            className="w-3.5 h-3.5 accent-eb-500"
                          />
                        </td>
                        <td className="px-3 py-2 mono text-xs text-eb-500 font-semibold">
                          {t.task_id ?? String(t.id)}
                        </td>
                        <td className="px-3 py-2">
                          <span className="text-slate-900 font-medium">
                            {t.title ?? "(no title)"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {t.feature_id ? (
                            <span className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded mono">
                              {t.feature_id}
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${badge.className}`}
                          >
                            {badge.label}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {t.assignee_name || t.assignee ? (
                            <span>{t.assignee_name ?? t.assignee}</span>
                          ) : (
                            <span className="text-slate-400">unassigned</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right tabular text-xs">
                          {typeof t.estimate_hours === "number"
                            ? `${t.estimate_hours}h`
                            : "—"}
                        </td>
                        <td className="px-3 py-2 text-right tabular text-xs mono">
                          {typeof t.cost === "number"
                            ? `¥${t.cost}`
                            : "—"}
                        </td>
                        <td className="px-3 py-2 text-xs text-slate-500 mono">
                          {t.updated_at ?? "—"}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            aria-label="操作メニュー"
                            className="text-slate-400 hover:text-slate-900"
                          >
                            <MoreVertical
                              className="w-3.5 h-3.5"
                              aria-hidden
                            />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                <span data-testid="task-list-count">
                  {visibleTasks.length} / {tasks.length} 件表示
                </span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    aria-label="前のページ"
                    disabled
                    className="px-2 py-1 rounded hover:bg-slate-50 text-slate-400"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" aria-hidden />
                  </button>
                  <span className="px-3 py-1 mono">1 / 1</span>
                  <button
                    type="button"
                    aria-label="次のページ"
                    className="px-2 py-1 rounded hover:bg-slate-50"
                  >
                    <ChevronRight className="w-3.5 h-3.5" aria-hidden />
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </main>
  );
}
