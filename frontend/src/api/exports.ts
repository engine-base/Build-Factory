/**
 * T-V3-C-22 / F-031: Typed client for the Export pipeline endpoints backing
 * the S-061 (仕様書 PDF) and adjacent S-062 (納品レポート) preview screens.
 *
 * Backend contracts:
 *   POST /api/workspaces/{id}/exports       — queue spec_pdf / delivery_report job
 *   GET  /api/exports/{id}                  — poll status, fetch download_url
 *
 * OpenAPI:
 *   docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1workspaces~1{id}~1exports
 *   docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1exports~1{id}
 *
 * Implementation seed (backend, REUSE/REFACTOR):
 *   backend/routers/workspaces.py::post_workspaces_by_id_exports
 *   backend/routers/exports.py::get_exports_by_id
 *
 * The thrown {@link ExportApiError} surfaces a non-technical message tagged
 * with the failing endpoint so the UI toast can satisfy AC-F1 (UNWANTED 4xx/5xx
 * → endpoint-referenced toast, no server stack-trace leak).
 *
 * @screen-id S-061
 * @feature-id F-031
 * @task-ids T-V3-C-22
 * @entities E-014
 * @phase Phase 1B
 */

export const EXPORTS_BY_WORKSPACE_ENDPOINT_TEMPLATE =
  "/api/workspaces/{id}/exports";
export const EXPORT_BY_ID_ENDPOINT_TEMPLATE = "/api/exports/{id}";

/** Render `POST /api/workspaces/{id}/exports` with the workspace UUID inlined. */
export function buildExportsByWorkspaceEndpoint(workspaceId: string): string {
  return EXPORTS_BY_WORKSPACE_ENDPOINT_TEMPLATE.replace(
    "{id}",
    encodeURIComponent(workspaceId),
  );
}

/** Render `GET /api/exports/{id}` with the export UUID inlined. */
export function buildExportByIdEndpoint(exportId: string): string {
  return EXPORT_BY_ID_ENDPOINT_TEMPLATE.replace(
    "{id}",
    encodeURIComponent(exportId),
  );
}

// ---------------------------------------------------------------------------
// Schema (mirrors openapi.yaml#/components/schemas/Export + request body)
// ---------------------------------------------------------------------------

/** Export job types supported by the backend (openapi.yaml#enum). */
export type ExportType = "spec_pdf" | "delivery_report";

/** Lifecycle status of an export job (informational; backend authoritative). */
export type ExportStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface ExportRecord {
  id: string;
  type?: ExportType | string;
  status?: ExportStatus | string;
  workspace_id?: string | number | null;
  created_at?: string;
  updated_at?: string;
  /** Tolerate unknown server-side metadata (kept additive). */
  [extra: string]: unknown;
}

/** Response envelope for POST /api/workspaces/{id}/exports. */
export interface ExportQueueResponse {
  export_id: string;
  status: string;
}

/** Response envelope for GET /api/exports/{id}. */
export interface ExportStatusResponse {
  export: ExportRecord | null;
  /** null while status is queued / running (AC-F3). */
  download_url: string | null;
}

/** Request body for POST /api/workspaces/{id}/exports. */
export interface QueueExportRequest {
  type: ExportType;
  /** Optional renderer options (page size, watermark, …). */
  options?: Record<string, unknown> | string;
}

// ---------------------------------------------------------------------------
// Error type (parity with auth.ApiError / EmailApiError shape)
// ---------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象が見つかりませんでした",
  409: "競合する状態のため操作を完了できませんでした",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/**
 * Structured error for the /api/exports/* + /api/workspaces/{id}/exports
 * endpoints. `toUserMessage()` produces a non-technical sentence referencing
 * the failing endpoint without leaking server stack traces (AC-F1).
 */
export class ExportApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "ExportApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-061 UNWANTED): produce a non-technical, user-facing message that
   * references the failing endpoint without exposing server stack traces.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

interface ClientInit {
  fetchImpl?: typeof fetch;
  baseUrl?: string;
  /** Bearer access token (workspace member scope required by backend). */
  token?: string;
  signal?: AbortSignal;
}

function resolveBaseUrl(init?: ClientInit): string {
  if (init?.baseUrl) return init.baseUrl;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  return "http://localhost:8001";
}

function buildHeaders(init?: ClientInit, withBody = false): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (withBody) headers["Content-Type"] = "application/json";
  if (init?.token) headers["Authorization"] = `Bearer ${init.token}`;
  return headers;
}

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<ExportApiError> {
  let code = "UNKNOWN";
  let message = response.statusText || "request failed";
  try {
    const payload = (await response.json()) as BackendErrorEnvelope;
    if (payload && typeof payload.detail === "object" && payload.detail) {
      if (typeof payload.detail.code === "string") code = payload.detail.code;
      if (typeof payload.detail.message === "string")
        message = payload.detail.message;
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. We deliberately do NOT
    // embed the raw body to avoid leaking server stack traces (AC-F1).
  }
  return new ExportApiError(code, message, response.status, endpoint);
}

// ---------------------------------------------------------------------------
// POST /api/workspaces/{id}/exports — queue export job
// ---------------------------------------------------------------------------

/**
 * Queue a PDF / report export job (AC-F2).
 *
 * EVENT-DRIVEN: When the user clicks the "PDF ダウンロード" button on S-061,
 * the system shall POST to /api/workspaces/{id}/exports with type=spec_pdf
 * and surface the returned export_id within 1 second.
 *
 * @throws ExportApiError on 4xx / 5xx / network failure.
 */
export async function queueExport(
  workspaceId: string,
  payload: QueueExportRequest,
  init?: ClientInit,
): Promise<ExportQueueResponse> {
  const endpoint = buildExportsByWorkspaceEndpoint(workspaceId);
  const base = resolveBaseUrl(init);
  const fetchImpl = init?.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(`${base}${endpoint}`, {
      method: "POST",
      headers: buildHeaders(init, true),
      body: JSON.stringify(payload),
      signal: init?.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new ExportApiError(
      "export.network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) throw await parseError(response, endpoint);

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  const obj = (data ?? {}) as { export_id?: unknown; status?: unknown };
  return {
    export_id: typeof obj.export_id === "string" ? obj.export_id : "",
    status: typeof obj.status === "string" ? obj.status : "queued",
  };
}

// ---------------------------------------------------------------------------
// GET /api/exports/{id} — poll status, fetch download_url
// ---------------------------------------------------------------------------

/**
 * Fetch export status + download URL (AC-F3).
 *
 * STATE-DRIVEN: While an export status is 'queued' or 'running', the system
 * shall surface download_url=null so the UI keeps the download CTA disabled.
 *
 * @throws ExportApiError on 4xx / 5xx / network failure.
 */
export async function getExportById(
  exportId: string,
  init?: ClientInit,
): Promise<ExportStatusResponse> {
  const endpoint = buildExportByIdEndpoint(exportId);
  const base = resolveBaseUrl(init);
  const fetchImpl = init?.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(`${base}${endpoint}`, {
      method: "GET",
      headers: buildHeaders(init),
      signal: init?.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new ExportApiError(
      "export.network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) throw await parseError(response, endpoint);

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  const obj = (data ?? {}) as {
    export?: ExportRecord | null;
    download_url?: unknown;
  };
  const downloadUrl =
    typeof obj.download_url === "string" && obj.download_url.length > 0
      ? obj.download_url
      : null;
  return {
    export: obj.export ?? null,
    download_url: downloadUrl,
  };
}

/**
 * Convenience: tell whether the given status string is in a "terminal,
 * downloadable" state. Used by S-061 to enable / disable the download CTA.
 */
export function isExportDownloadable(
  status: string | undefined | null,
): boolean {
  return status === "succeeded";
}
