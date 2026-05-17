"use client";

/**
 * T-V3-C-43 / S-041 — 監査ログ (Audit Log Viewer) page.
 *
 * Mock source of truth:   docs/mocks/2026-05-15_v3/ops/S-041-audit-log-viewer.html
 * Spec source of truth:   docs/functional-breakdown/2026-05-16_v3/screens.json#S-041
 * Feature source:         docs/functional-breakdown/2026-05-16_v3/features.json#F-018
 * Backend contracts:      backend/routers/audit_logs.py (T-V3-B-024)
 *                         - GET /api/audit-logs
 *                         - GET /api/audit-logs/export.csv
 *                         - GET /api/audit-logs/export.json
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-041
 * @feature-id F-018
 * @task-ids T-V3-C-43
 * @entities E-029
 * @phase Phase 1
 *
 * 3-tier AC mapping (逐語 from docs/audit/2026-05-16_v3/T-V3-C-43.md):
 *   structural.AC-S1 (h1 "監査ログ")                                  — H1 below.
 *   structural.AC-S2 (Lucide icons exclusively, no emoji)              — lucide-react imports.
 *   functional.AC-F1 (GET /api/audit-logs + 4xx toast + empty state)   — useAuditLogViewer.
 *   functional.AC-F2 (401 → redirect /login, no workspace data)        — useEffect router.replace.
 *   functional.AC-F3 (audit_log entry written within 1s per mutation)  — enforced server-side
 *                     by backend/services/audit_logs.py on every write endpoint;
 *                     this page is read-only and surfaces those records.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Activity,
  AlertTriangle,
  ArrowDownToLine,
  Braces,
  ChevronLeft,
  ChevronRight,
  Download,
  GitCompare,
  Loader2,
  RefreshCw,
  Search as SearchIcon,
} from "lucide-react";

import {
  AUDIT_LOG_TIME_RANGES,
  type AuditLogTimeRange,
  useAuditLogViewer,
} from "@/hooks/use-audit-log-viewer";
import type { AuditLogEntry } from "@/lib/api/audit-log-viewer";

// Mock-derived heading text (S-041 h1) — kept as a const so the structural
// lint can grep for the literal and the AC-S1 mapping stays explicit.
const H1_TEXT = "監査ログ";
const PAGE_DESCRIPTION =
  "全アクション履歴 / before/after diff / 7 年保管 / 改ざん検知";

// Action chip colour map — mirrors the mock palette.
function actionChipClass(action: string): string {
  if (action.startsWith("redline")) {
    return "bg-red-100 text-red-700 border-red-300 font-bold";
  }
  if (
    action.startsWith("delete") ||
    action.startsWith("schema_change") ||
    action.includes(".delete")
  ) {
    return "bg-red-50 text-red-700 border-red-200";
  }
  if (action.startsWith("user.") || action.startsWith("auth")) {
    return "bg-blue-50 text-blue-700 border-blue-200";
  }
  if (
    action.includes("update") ||
    action.startsWith("constitution") ||
    action.startsWith("workspace.update")
  ) {
    return "bg-amber-50 text-amber-700 border-amber-200";
  }
  return "bg-emerald-50 text-emerald-700 border-emerald-200";
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // YYYY-MM-DD HH:mm:ss (UTC fallback to avoid hydration drift)
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

function describeTarget(row: AuditLogEntry): string {
  if (row.resource_type) {
    return row.resource_id != null
      ? `${row.resource_type}/${row.resource_id}`
      : row.resource_type;
  }
  return "—";
}

function describeActor(row: AuditLogEntry): string {
  if (row.actor_user_id) return row.actor_user_id;
  if (row.actor_persona) return row.actor_persona;
  return "system";
}

function detailSummary(row: AuditLogEntry): string {
  const payload = row.payload ?? {};
  if (typeof payload.summary === "string") return payload.summary;
  if (typeof payload.message === "string") return payload.message;
  if ("before" in payload || "after" in payload) {
    return "before/after diff";
  }
  return row.success === false ? "failure" : "";
}

export default function AuditLogViewerPage() {
  const router = useRouter();
  const {
    filters,
    setFilter,
    resetFilters,
    rows,
    total,
    visibleTotal,
    isLoading,
    isError,
    errorMessage,
    unauthenticated,
    refetch,
    exportCsv,
    exportJson,
    exporting,
  } = useAuditLogViewer();

  // AC-F2: 401 → redirect to /login (S-001). Guard against repeated effects
  // by short-circuiting if the flag flips back to false.
  React.useEffect(() => {
    if (unauthenticated) {
      router.replace("/login");
    }
  }, [unauthenticated, router]);

  // AC-F1: surface non-technical error toast referencing /api/audit-logs.
  const lastToastedRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!errorMessage) {
      lastToastedRef.current = null;
      return;
    }
    if (unauthenticated) {
      // The redirect effect handles UX — skip a duplicate toast.
      lastToastedRef.current = errorMessage;
      return;
    }
    if (lastToastedRef.current !== errorMessage) {
      toast.error(errorMessage);
      lastToastedRef.current = errorMessage;
    }
  }, [errorMessage, unauthenticated]);

  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const selected = React.useMemo(
    () => rows.find((r) => r.id === selectedId) ?? null,
    [rows, selectedId],
  );

  const showEmptyState = !isLoading && rows.length === 0;

  return (
    <div
      data-screen-id="S-041"
      data-feature-id="F-018"
      data-task-ids="T-V3-C-43"
      data-entities="E-029"
      data-phase="Phase 1"
      className="min-h-full bg-slate-50"
    >
      <div className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-end justify-between mb-3 gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Activity className="w-6 h-6 text-eb-500" aria-hidden />
              {H1_TEXT}
            </h1>
            <p className="text-sm text-slate-600 mt-1">{PAGE_DESCRIPTION}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isLoading}
              data-testid="audit-log-refresh"
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2 disabled:opacity-60"
              aria-label="refresh"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              ) : (
                <RefreshCw className="w-4 h-4" aria-hidden />
              )}
              <span>更新</span>
            </button>
            <button
              type="button"
              onClick={() => {
                void exportCsv();
              }}
              disabled={exporting !== null}
              data-testid="audit-log-export-csv"
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2 disabled:opacity-60"
            >
              {exporting === "csv" ? (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              ) : (
                <Download className="w-4 h-4" aria-hidden />
              )}
              CSV export
            </button>
            <button
              type="button"
              onClick={() => {
                void exportJson();
              }}
              disabled={exporting !== null}
              data-testid="audit-log-export-json"
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2 disabled:opacity-60"
            >
              {exporting === "json" ? (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              ) : (
                <Braces className="w-4 h-4" aria-hidden />
              )}
              JSON export
            </button>
          </div>
        </div>

        {/* Filter bar — mirrors S-041 mock */}
        <div
          className="flex items-center gap-2 flex-wrap"
          role="group"
          aria-label="監査ログフィルター"
        >
          <div className="relative flex-1 max-w-[260px]">
            <SearchIcon
              className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"
              aria-hidden
            />
            <input
              type="search"
              placeholder="検索: action / user / target"
              value={filters.query}
              onChange={(e) => setFilter("query", e.target.value)}
              data-testid="audit-log-filter-query"
              aria-label="検索"
              className="border border-slate-200 text-xs h-8 pl-7 pr-2 rounded-md w-full focus:outline-none focus:border-eb-500"
            />
          </div>
          <select
            value={filters.user}
            onChange={(e) => setFilter("user", e.target.value)}
            data-testid="audit-log-filter-user"
            aria-label="user フィルター"
            className="border border-slate-200 text-xs h-8 px-2 rounded-md"
          >
            <option value="all">全 user</option>
            <option value="masato">masato</option>
            <option value="devon">devon (AI)</option>
            <option value="system">system</option>
          </select>
          <select
            value={filters.action}
            onChange={(e) => setFilter("action", e.target.value)}
            data-testid="audit-log-filter-action"
            aria-label="action フィルター"
            className="border border-slate-200 text-xs h-8 px-2 rounded-md"
          >
            <option value="all">全 action</option>
            <option value="create">create</option>
            <option value="update">update</option>
            <option value="delete">delete</option>
            <option value="auth">auth</option>
            <option value="redline">red-line</option>
          </select>
          <select
            value={filters.range}
            onChange={(e) =>
              setFilter("range", e.target.value as AuditLogTimeRange)
            }
            data-testid="audit-log-filter-range"
            aria-label="期間フィルター"
            className="border border-slate-200 text-xs h-8 px-2 rounded-md"
          >
            {AUDIT_LOG_TIME_RANGES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={resetFilters}
            data-testid="audit-log-filter-reset"
            className="text-xs text-slate-500 hover:text-slate-900"
          >
            filter リセット
          </button>
          <span
            className="ml-auto text-xs text-slate-500 font-mono"
            data-testid="audit-log-counter"
          >
            {visibleTotal.toLocaleString()} 件 / 全 {total.toLocaleString()} 件
          </span>
        </div>
      </div>

      {/* Inline error banner — paired with the toast for AC-F1. */}
      {isError && !unauthenticated ? (
        <div
          role="alert"
          data-testid="audit-log-error"
          className="mx-6 mt-4 flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden />
          <span>{errorMessage}</span>
        </div>
      ) : null}

      <div className="bg-white">
        <table className="w-full text-sm" data-testid="audit-log-table">
          <thead className="bg-slate-50 sticky top-0">
            <tr className="text-[10px] uppercase tracking-wider text-slate-500">
              <th className="px-3 py-2 text-left w-32">時刻</th>
              <th className="px-3 py-2 text-left">User</th>
              <th className="px-3 py-2 text-left">Action</th>
              <th className="px-3 py-2 text-left">Target</th>
              <th className="px-3 py-2 text-left">Detail</th>
              <th className="px-3 py-2 text-right w-32">IP / source</th>
            </tr>
          </thead>
          <tbody>
            {showEmptyState ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-3 py-10 text-center text-sm text-slate-500"
                  data-testid="audit-log-empty"
                >
                  {isError
                    ? "監査ログを取得できませんでした"
                    : "条件に一致するログはありません"}
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const isSelected = selectedId === row.id;
                const ip =
                  (row.payload?.ip_address as string | undefined) ??
                  (row.payload?.source as string | undefined) ??
                  "—";
                return (
                  <tr
                    key={row.id}
                    onClick={() =>
                      setSelectedId((prev) => (prev === row.id ? null : row.id))
                    }
                    data-testid={`audit-log-row-${row.id}`}
                    className={
                      "border-t border-slate-100 hover:bg-slate-50 cursor-pointer " +
                      (row.action.startsWith("redline")
                        ? "border-t border-red-200 bg-red-50 hover:bg-red-100 "
                        : "") +
                      (isSelected ? "bg-amber-50/40 " : "")
                    }
                  >
                    <td className="px-3 py-2 font-mono text-xs text-slate-500">
                      {formatTimestamp(row.created_at)}
                    </td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 text-xs">
                        {describeActor(row)}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={
                          "text-[11px] px-2 py-0.5 rounded-full font-medium font-mono border " +
                          actionChipClass(row.action)
                        }
                      >
                        {row.action}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {describeTarget(row)}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">
                      {detailSummary(row)}
                    </td>
                    <td className="px-3 py-2 text-right text-xs text-slate-500 font-mono">
                      {ip}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {selected ? (
          <div
            className="border-t border-amber-200 bg-amber-50/30 p-5"
            data-testid="audit-log-diff"
          >
            <div className="text-xs text-slate-500 font-semibold mb-2 flex items-center gap-2">
              <GitCompare className="w-3.5 h-3.5" aria-hidden />
              {selected.action} → diff
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="bg-white border border-red-200 rounded-md p-3">
                <div className="text-[10px] uppercase tracking-wider text-red-600 font-bold mb-1">
                  Before
                </div>
                <pre className="font-mono text-xs text-slate-700 leading-relaxed whitespace-pre-wrap break-all">
                  {JSON.stringify(
                    (selected.payload?.before as unknown) ?? {},
                    null,
                    2,
                  )}
                </pre>
              </div>
              <div className="bg-white border border-emerald-200 rounded-md p-3">
                <div className="text-[10px] uppercase tracking-wider text-emerald-600 font-bold mb-1">
                  After
                </div>
                <pre className="font-mono text-xs text-slate-700 leading-relaxed whitespace-pre-wrap break-all">
                  {JSON.stringify(
                    (selected.payload?.after as unknown) ?? {},
                    null,
                    2,
                  )}
                </pre>
              </div>
            </div>
          </div>
        ) : null}

        <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>
            {visibleTotal.toLocaleString()} 件表示 / 全 {total.toLocaleString()} 件
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="px-2 py-1 rounded hover:bg-slate-50 disabled:opacity-30"
              disabled
              aria-label="前のページ"
            >
              <ChevronLeft className="w-3.5 h-3.5" aria-hidden />
            </button>
            <span className="px-3 py-1 font-mono">1 / 1</span>
            <button
              type="button"
              className="px-2 py-1 rounded hover:bg-slate-50 disabled:opacity-30"
              disabled
              aria-label="次のページ"
            >
              <ChevronRight className="w-3.5 h-3.5" aria-hidden />
            </button>
          </div>
        </div>
      </div>

      {/* Decorative hidden icon to keep tree-shaking-aware compilers from
          dropping the lucide download alias if the export buttons are unused
          in a future redesign. (visually hidden, role=none) */}
      <span className="sr-only" aria-hidden>
        <ArrowDownToLine className="w-3 h-3" />
      </span>
    </div>
  );
}
