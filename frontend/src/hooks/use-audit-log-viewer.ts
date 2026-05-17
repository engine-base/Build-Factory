/**
 * T-V3-C-43 / F-018 / S-041: Hook driving the audit_log_viewer page.
 *
 * Responsibilities:
 *  - Hold filter state (search query / user / action / time range).
 *  - Issue GET /api/audit-logs via the typed client and surface 4xx errors
 *    as a non-technical toast (AC-F1).
 *  - Trigger CSV / JSON export downloads (AC-F1 export endpoints).
 *  - Detect 401 responses and bubble an `unauthenticated` flag so the page
 *    can redirect to /login (S-001) (AC-F2).
 *
 * NOTE: AC-F3 (write an audit_log entry for every state-mutating API call)
 * is satisfied server-side by `backend/services/audit_logs.py` — every
 * write endpoint in this codebase passes through it. This hook is read-only.
 */

"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import {
  AUDIT_LOGS_ENDPOINT,
  AuditLogApiError,
  type AuditLogEntry,
  type AuditLogFilter,
  type AuditLogListResponse,
  fetchAuditLogs,
  fetchAuditLogsExportCsv,
  fetchAuditLogsExportJson,
  triggerBlobDownload,
} from "@/lib/api/audit-log-viewer";

export interface AuditLogViewerFilters {
  /** Free-text search applied to action / target / actor. */
  query: string;
  /** `actor_user_id` filter — "all" sentinel = no filter. */
  user: string;
  /** `action` filter — "all" sentinel = no filter. */
  action: string;
  /** Time range key — translated to from/to on the wire. */
  range: AuditLogTimeRange;
}

export type AuditLogTimeRange = "all" | "24h" | "7d" | "30d";

export const DEFAULT_FILTERS: AuditLogViewerFilters = {
  query: "",
  user: "all",
  action: "all",
  range: "all",
};

export const AUDIT_LOG_TIME_RANGES: { value: AuditLogTimeRange; label: string }[] = [
  { value: "all", label: "全期間" },
  { value: "24h", label: "過去 24h" },
  { value: "7d", label: "過去 7 日" },
  { value: "30d", label: "過去 30 日" },
];

function rangeToFromIso(range: AuditLogTimeRange, now: Date = new Date()): string | null {
  if (range === "all") return null;
  const ms = { "24h": 24 * 3600_000, "7d": 7 * 86400_000, "30d": 30 * 86400_000 }[range];
  return new Date(now.getTime() - ms).toISOString();
}

/**
 * Build an `AuditLogFilter` (wire shape) from the UI filter state.
 * Exported for tests so we can assert that the right query params get sent.
 */
export function buildWireFilter(state: AuditLogViewerFilters): AuditLogFilter {
  const filter: AuditLogFilter = {};
  if (state.user && state.user !== "all") filter.user_id = state.user;
  if (state.action && state.action !== "all") filter.action = state.action;
  const fromIso = rangeToFromIso(state.range);
  if (fromIso) filter.from_ = fromIso;
  return filter;
}

/**
 * Apply free-text search client-side. The backend `GET /api/audit-logs`
 * does not yet support a `q=` parameter, so we filter the 2xx body on
 * `action`, `actor_user_id`, `resource_type` and `resource_id`. The
 * filter is case-insensitive and treats empty strings as a no-op.
 */
export function applyFreeTextSearch(
  rows: AuditLogEntry[],
  query: string,
): AuditLogEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((row) => {
    const haystack = [
      row.action,
      row.actor_user_id ?? "",
      row.actor_persona ?? "",
      row.resource_type ?? "",
      row.resource_id != null ? String(row.resource_id) : "",
    ]
      .join("")
      .toLowerCase();
    return haystack.includes(q);
  });
}

export interface UseAuditLogViewerResult {
  filters: AuditLogViewerFilters;
  setFilter: <K extends keyof AuditLogViewerFilters>(
    key: K,
    value: AuditLogViewerFilters[K],
  ) => void;
  resetFilters: () => void;
  rows: AuditLogEntry[];
  total: number;
  visibleTotal: number;
  isLoading: boolean;
  isError: boolean;
  error: AuditLogApiError | null;
  errorMessage: string | null;
  /** True when the backend returned 401 — the page should redirect to /login (S-001). */
  unauthenticated: boolean;
  refetch: () => void;
  exportCsv: () => Promise<void>;
  exportJson: () => Promise<void>;
  exporting: "csv" | "json" | null;
}

/**
 * Main hook for S-041. Returns immutable filter state + query data.
 */
export function useAuditLogViewer(): UseAuditLogViewerResult {
  const [filters, setFilters] =
    React.useState<AuditLogViewerFilters>(DEFAULT_FILTERS);
  const [exporting, setExporting] = React.useState<"csv" | "json" | null>(null);
  const [exportError, setExportError] = React.useState<string | null>(null);

  const wireFilter = React.useMemo(() => buildWireFilter(filters), [filters]);

  const query = useQuery<AuditLogListResponse, AuditLogApiError>({
    queryKey: ["audit-logs", wireFilter] as const,
    queryFn: async ({ signal }) => {
      try {
        return await fetchAuditLogs(wireFilter, { signal });
      } catch (e) {
        if (e instanceof AuditLogApiError) throw e;
        throw new AuditLogApiError(
          "audit_log.unknown",
          (e as Error)?.message ?? "unknown error",
          0,
          AUDIT_LOGS_ENDPOINT,
        );
      }
    },
    retry: false,
    staleTime: 30_000,
  });

  const rows = React.useMemo(() => {
    const items = query.data?.items ?? [];
    return applyFreeTextSearch(items, filters.query);
  }, [query.data, filters.query]);

  const errorMessage = React.useMemo<string | null>(() => {
    if (exportError) return exportError;
    if (!query.isError) return null;
    return query.error?.toUserMessage() ?? "監査ログの取得に失敗しました";
  }, [exportError, query.isError, query.error]);

  const setFilter = React.useCallback(
    <K extends keyof AuditLogViewerFilters>(
      key: K,
      value: AuditLogViewerFilters[K],
    ) => {
      setFilters((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  const resetFilters = React.useCallback(() => {
    setFilters(DEFAULT_FILTERS);
  }, []);

  const runExport = React.useCallback(
    async (fmt: "csv" | "json") => {
      setExportError(null);
      setExporting(fmt);
      try {
        if (fmt === "csv") {
          const body = await fetchAuditLogsExportCsv(wireFilter);
          triggerBlobDownload(body, "audit-logs.csv", "text/csv;charset=utf-8");
        } else {
          const items = await fetchAuditLogsExportJson(wireFilter);
          triggerBlobDownload(
            JSON.stringify(items, null, 2),
            "audit-logs.json",
            "application/json",
          );
        }
      } catch (e) {
        if (e instanceof AuditLogApiError) {
          setExportError(e.toUserMessage());
        } else {
          setExportError(
            `監査ログの ${fmt.toUpperCase()} エクスポートに失敗しました`,
          );
        }
      } finally {
        setExporting(null);
      }
    },
    [wireFilter],
  );

  const exportCsv = React.useCallback(() => runExport("csv"), [runExport]);
  const exportJson = React.useCallback(() => runExport("json"), [runExport]);

  const unauthenticated = query.isError && query.error?.status === 401;

  return {
    filters,
    setFilter,
    resetFilters,
    rows,
    total: query.data?.total ?? rows.length,
    visibleTotal: rows.length,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error ?? null,
    errorMessage,
    unauthenticated: Boolean(unauthenticated),
    refetch: () => {
      query.refetch();
    },
    exportCsv,
    exportJson,
    exporting,
  };
}
