/**
 * T-V3-C-61 / S-012 / F-006,F-007,F-008,F-026 — Typed client for the workspace
 * dashboard endpoints backing the S-012 (案件ダッシュボード) screen.
 *
 * Backend contracts (T-V3-B-006/007/008/026/027 implemented):
 *   GET /api/workspaces/{id}/dashboard      — backend/routers/workspaces.py::get_workspaces_by_id_dashboard
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *   #/paths/~1api~1workspaces~1{id}~1dashboard
 *
 * Errors follow the project-wide {detail: {code, message}} contract. The
 * thrown {@link WorkspaceDashboardApiError} surfaces a non-technical,
 * endpoint-tagged message for UI toasts (AC-F1 / S-012) and never leaks
 * server stack traces or backend exception class names.
 */
import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function workspaceDashboardEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/dashboard`;
}

// --------------------------------------------------------------------------
// Wire types — mirror openapi.yaml + S-012 mock fixtures.
// --------------------------------------------------------------------------

/** Per-KPI tile shown in the top metrics row of S-012. */
export interface DashboardKpi {
  /**
   * Logical label key. The S-012 KPI label set is enforced by the mock:
   *   {Phase 進捗 / Tasks / Running Sessions / Cost (this month)}.
   * Backend may add more keys; the UI silently ignores unknown keys.
   */
  label: string;
  value: number | string;
  /** Optional secondary text (e.g. "残 13 件", "予算 ¥10,000"). */
  hint?: string | null;
  /** Optional progress 0..100 for the progress-bar variant (Phase 進捗). */
  progress?: number | null;
}

/** A row of the "最近のタスク" table (mirrors openapi Task schema subset). */
export interface DashboardTaskRow {
  id: string;
  title: string;
  /** "todo" | "running" | "review" | "done" | other (open-ended). */
  status: string;
  assignee?: string | null;
  /** Human-readable "x min ago" string from the server. */
  updated_label?: string | null;
}

/** A row of "Pending Reviews (n)" — PR / 赤線 / 納品 etc. */
export interface DashboardPendingReview {
  id: string;
  /** "PR" | "赤線" | "納品" — open-ended chip text. */
  kind: string;
  title: string;
  /** "PR #283 · 12 min ago" — open-ended detail label. */
  detail?: string | null;
}

/** A row of "Running Sessions (n)" — live swarm activity. */
export interface DashboardSession {
  id: string;
  task_id?: string | null;
  title: string;
  /** "running" | "paused" — drives the indicator color. */
  status: string;
  /** Persona initials (DV / QN / WS / MR). */
  persona?: string | null;
  /** "12 min · ¥41" — open-ended detail label. */
  detail?: string | null;
}

/** Current phase summary (mirrors phases list head). */
export interface DashboardPhase {
  id: string;
  name: string;
  /** "running" | "locked" | "completed" — open-ended. */
  status: string;
  /** "23 / 36 task done" — open-ended subtitle. */
  subtitle?: string | null;
}

/** GET /api/workspaces/{id}/dashboard 2xx body. */
export interface WorkspaceDashboardResponse {
  workspace: {
    id: string;
    name: string;
    /** "Phase 1 開発 / 受託 SaaS の dogfood 検証" — mock subtitle. */
    description?: string | null;
  };
  kpi: DashboardKpi[];
  current_phase?: DashboardPhase | null;
  next_phase?: DashboardPhase | null;
  constitution?: { items: string[] } | null;
  recent_tasks: DashboardTaskRow[];
  pending_reviews: DashboardPendingReview[];
  sessions_running_count?: number | null;
  sessions: DashboardSession[];
}

// --------------------------------------------------------------------------
// Error class (AC-F1: 4xx surfaces non-leaky message)
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "入力内容を確認してください",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "案件ダッシュボードが見つかりませんでした",
  409: "ダッシュボードの状態が一致しません",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/** Thrown for any non-2xx response from the workspace-dashboard endpoint. */
export class WorkspaceDashboardApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "WorkspaceDashboardApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * Build a non-technical, endpoint-tagged user-facing message.
   * Never leaks server stack traces (AC-F1). The endpoint stays visible so
   * QA / support can correlate without exposing internals.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal HTTP helper
// --------------------------------------------------------------------------

export interface WorkspaceDashboardRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) — member role required. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: WorkspaceDashboardRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<WorkspaceDashboardApiError> {
  let code = "UNKNOWN";
  let message = response.statusText || "request failed";
  try {
    const payload = (await response.json()) as BackendErrorEnvelope;
    if (payload && typeof payload.detail === "object" && payload.detail) {
      if (typeof payload.detail.code === "string") code = payload.detail.code;
      if (typeof payload.detail.message === "string") {
        message = payload.detail.message;
      }
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. Never leak raw body.
  }
  return new WorkspaceDashboardApiError(
    code,
    message,
    response.status,
    endpoint,
  );
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

/**
 * GET /api/workspaces/{id}/dashboard — fetch the full S-012 dashboard payload
 * (KPIs + current phase + constitution snapshot + recent tasks + pending
 * reviews + running sessions) for the given workspace.
 */
export async function getWorkspaceDashboard(
  workspaceId: string,
  opts: WorkspaceDashboardRequestOptions = {},
): Promise<WorkspaceDashboardResponse> {
  const endpoint = workspaceDashboardEndpoint(workspaceId);
  const base = resolveApiBase(opts);
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (opts.authToken) {
    headers.Authorization = `Bearer ${opts.authToken}`;
  }

  let response: Response;
  try {
    response = await fetchImpl(`${base}${endpoint}`, {
      method: "GET",
      headers,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new WorkspaceDashboardApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  return (await response.json()) as WorkspaceDashboardResponse;
}
