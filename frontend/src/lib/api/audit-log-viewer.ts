/**
 * T-V3-C-43 / F-018 / S-041: Typed client for the audit_log_viewer screen.
 *
 * Backend contracts (existing, owned by T-V3-B-24):
 *   GET /api/audit-logs                — list (items + total) for workspace_admin
 *   GET /api/audit-logs/export.csv     — CSV stream (Content-Disposition attachment)
 *   GET /api/audit-logs/export.json    — JSON array wrapper {json_body: [...]}
 *
 * Backend router  : backend/routers/audit_logs.py
 * Backend schema  : backend/schemas/audit_logs.py (E-037 AuditLog)
 * OpenAPI source  : docs/api-design/2026-05-16_v3/openapi.yaml (/api/audit-logs*)
 *
 * Error contract  : `{detail: {code, message}}` (FastAPI project-wide).
 *                   Thrown as AuditLogApiError so the UI can surface a
 *                   non-technical toast referencing the failing endpoint
 *                   without leaking server stack traces.
 *
 * Auth: workspace_admin only. Unauthenticated (401) callers are redirected
 * to /login (S-001) by the page-level guard — see use-audit-log-viewer.ts.
 */

export const AUDIT_LOGS_ENDPOINT = "/api/audit-logs";
export const AUDIT_LOGS_EXPORT_CSV_ENDPOINT = "/api/audit-logs/export.csv";
export const AUDIT_LOGS_EXPORT_JSON_ENDPOINT = "/api/audit-logs/export.json";

/**
 * Single audit log entry — mirrors backend Pydantic `AuditLog` (E-037).
 * `payload` carries the `before` / `after` diff snapshots referenced by the
 * S-041 mock when rendering the inline diff card.
 */
export interface AuditLogEntry {
  id: number;
  workspace_id?: number | null;
  actor_user_id?: string | null;
  actor_persona?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: number | null;
  payload?: Record<string, unknown>;
  success?: boolean;
  created_at?: string | null;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
}

export interface AuditLogJsonExportResponse {
  json_body: AuditLogEntry[];
}

/**
 * Filter input shared by all 3 endpoints. Fields are optional. `from_` is
 * serialised to `from` on the wire because `from` is a JS reserved word.
 */
export interface AuditLogFilter {
  workspace_id?: number | null;
  /** ISO-8601 (YYYY-MM-DD or full ISO). Wire name: `from`. */
  from_?: string | null;
  /** ISO-8601 (YYYY-MM-DD or full ISO). */
  to?: string | null;
  user_id?: string | null;
  action?: string | null;
}

/** Thrown for any non-2xx response from /api/audit-logs*. */
export class AuditLogApiError extends Error {
  code: string;
  status: number;
  endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "AuditLogApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1: produce a non-technical user-facing message that references the
   * failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly =
      AUDIT_LOG_USER_MESSAGES[this.status] ?? AUDIT_LOG_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const AUDIT_LOG_USER_MESSAGES: Record<number | "default", string> = {
  400: "監査ログのフィルターが不正です",
  401: "サインインが必要です",
  403: "監査ログを閲覧する権限がありません",
  404: "監査ログが見つかりません",
  422: "フィルター条件を確認してください (期間が広すぎる可能性があります)",
  429: "リクエスト回数の上限に達しました。しばらく待って再試行してください",
  500: "監査ログの取得に失敗しました。時間をおいて再試行してください",
  default: "監査ログの取得に失敗しました",
};

function resolveApiBase(opts: { apiBase?: string }): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

function buildFilterParams(filter: AuditLogFilter | undefined): URLSearchParams {
  const params = new URLSearchParams();
  if (!filter) return params;
  if (filter.workspace_id != null) {
    params.set("workspace_id", String(filter.workspace_id));
  }
  if (filter.from_) params.set("from", filter.from_);
  if (filter.to) params.set("to", filter.to);
  if (filter.user_id) params.set("user_id", filter.user_id);
  if (filter.action) params.set("action", filter.action);
  return params;
}

interface RequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
}

async function readErrorDetail(
  resp: Response,
): Promise<{ code: string; message: string }> {
  let code = "audit_log.unknown";
  let message = `HTTP ${resp.status}`;
  try {
    const data = (await resp.json()) as {
      detail?: { code?: string; message?: string } | string;
    };
    if (typeof data?.detail === "string") {
      message = data.detail;
    } else if (data?.detail && typeof data.detail === "object") {
      if (data.detail.code) code = data.detail.code;
      if (data.detail.message) message = data.detail.message;
    }
  } catch {
    // intentionally ignore — keep generic fallback (no server-trace leak).
  }
  return { code, message };
}

/**
 * AC-F1: GET /api/audit-logs?workspace_id=...&from=...&to=...&user_id=...&action=...
 * Returns the raw {items,total} body on 2xx. Throws AuditLogApiError otherwise.
 */
export async function fetchAuditLogs(
  filter: AuditLogFilter = {},
  opts: RequestOptions = {},
): Promise<AuditLogListResponse> {
  const base = resolveApiBase(opts);
  const params = buildFilterParams(filter);
  const qs = params.toString();
  const url = `${base}${AUDIT_LOGS_ENDPOINT}${qs ? `?${qs}` : ""}`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: opts.signal,
      credentials: "include",
    });
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") {
      throw e;
    }
    throw new AuditLogApiError(
      "audit_log.network_error",
      "network error",
      0,
      AUDIT_LOGS_ENDPOINT,
    );
  }

  if (!resp.ok) {
    const { code, message } = await readErrorDetail(resp);
    throw new AuditLogApiError(code, message, resp.status, AUDIT_LOGS_ENDPOINT);
  }

  return (await resp.json()) as AuditLogListResponse;
}

/**
 * AC-F1 (export): GET /api/audit-logs/export.csv?...
 * Returns the raw CSV body (text/csv stream). Throws AuditLogApiError on
 * non-2xx. Pairs with `triggerCsvDownload` to produce a Blob download.
 */
export async function fetchAuditLogsExportCsv(
  filter: AuditLogFilter = {},
  opts: RequestOptions = {},
): Promise<string> {
  const base = resolveApiBase(opts);
  const params = buildFilterParams(filter);
  const qs = params.toString();
  const url = `${base}${AUDIT_LOGS_EXPORT_CSV_ENDPOINT}${qs ? `?${qs}` : ""}`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "GET",
      headers: { Accept: "text/csv" },
      signal: opts.signal,
      credentials: "include",
    });
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") {
      throw e;
    }
    throw new AuditLogApiError(
      "audit_log.network_error",
      "network error",
      0,
      AUDIT_LOGS_EXPORT_CSV_ENDPOINT,
    );
  }

  if (!resp.ok) {
    const { code, message } = await readErrorDetail(resp);
    throw new AuditLogApiError(
      code,
      message,
      resp.status,
      AUDIT_LOGS_EXPORT_CSV_ENDPOINT,
    );
  }

  return await resp.text();
}

/**
 * AC-F1 (export): GET /api/audit-logs/export.json?...
 * Returns the unwrapped array (backend wraps it as `{json_body: [...]}`).
 */
export async function fetchAuditLogsExportJson(
  filter: AuditLogFilter = {},
  opts: RequestOptions = {},
): Promise<AuditLogEntry[]> {
  const base = resolveApiBase(opts);
  const params = buildFilterParams(filter);
  const qs = params.toString();
  const url = `${base}${AUDIT_LOGS_EXPORT_JSON_ENDPOINT}${qs ? `?${qs}` : ""}`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: opts.signal,
      credentials: "include",
    });
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") {
      throw e;
    }
    throw new AuditLogApiError(
      "audit_log.network_error",
      "network error",
      0,
      AUDIT_LOGS_EXPORT_JSON_ENDPOINT,
    );
  }

  if (!resp.ok) {
    const { code, message } = await readErrorDetail(resp);
    throw new AuditLogApiError(
      code,
      message,
      resp.status,
      AUDIT_LOGS_EXPORT_JSON_ENDPOINT,
    );
  }

  const body = (await resp.json()) as AuditLogJsonExportResponse | AuditLogEntry[];
  if (Array.isArray(body)) return body;
  return body.json_body ?? [];
}

/**
 * Browser-only helper: trigger a Blob download with the given filename.
 * Guarded for SSR (does nothing if `document` is not available).
 */
export function triggerBlobDownload(
  content: string,
  filename: string,
  mime: string,
): void {
  if (typeof document === "undefined" || typeof URL === "undefined") return;
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
