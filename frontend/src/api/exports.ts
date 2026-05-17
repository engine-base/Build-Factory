/**
 * T-V3-C-23 / F-031 / S-062: Typed client for the delivery / export endpoints
 * backing the 納品レポート screen.
 *
 * Backend contract (T-V3-B-21):
 *   GET  /api/workspaces/{id}/delivery               — backend/routers/workspaces.py::get_workspaces_by_id_delivery
 *   POST /api/workspaces/{id}/delivery/approve       — backend/routers/workspaces.py::post_workspaces_by_id_delivery_approve
 *   POST /api/workspaces/{id}/delivery/send-client   — backend/routers/workspaces.py::post_workspaces_by_id_delivery_send_client
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/paths/~1api~1workspaces~1{id}~1delivery
 *          #/paths/~1api~1workspaces~1{id}~1delivery~1approve
 *          #/paths/~1api~1workspaces~1{id}~1delivery~1send-client
 *
 * Auth model: bearerAuth (workspace member for GET, workspace_admin for POSTs).
 * The thrown {@link ExportsApiError} surfaces a non-technical message tagged
 * with the failing endpoint (AC-F1 / AC-F4 on S-062), never leaking server
 * stack traces.
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-23.md):
 *   functional.AC-F1 → `getWorkspaceDelivery(id)` GETs the delivery package.
 *                      4xx/5xx → ExportsApiError.toUserMessage() endpoint-tagged.
 *   functional.AC-F2 → `requestSpecPdfExport(id)` POSTs an export queue job and
 *                      returns the new export_id (best-effort within 1 second).
 *   functional.AC-F3 → `getExport(id)` returns download_url=null while status is
 *                      'queued' or 'running'; the page only enables the download
 *                      button once a download_url is present.
 */

// --------------------------------------------------------------------------
// Endpoint helpers (exposed so callers / tests can assert canonical paths).
// --------------------------------------------------------------------------

export const WORKSPACE_DELIVERY_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/delivery";
export const WORKSPACE_EXPORTS_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/exports";
export const EXPORT_BY_ID_ENDPOINT_PATTERN = "/api/exports/{id}";

/** Build the canonical /api/workspaces/{id}/delivery path. */
export function workspaceDeliveryEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/delivery`;
}

/** Build the canonical /api/workspaces/{id}/delivery/approve path. */
export function workspaceDeliveryApproveEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/delivery/approve`;
}

/** Build the canonical /api/workspaces/{id}/delivery/send-client path. */
export function workspaceDeliverySendClientEndpoint(
  workspaceId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/delivery/send-client`;
}

/** Build the canonical /api/workspaces/{id}/exports path. */
export function workspaceExportsEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/exports`;
}

/** Build the canonical /api/exports/{id} path. */
export function exportByIdEndpoint(exportId: string): string {
  return `/api/exports/${encodeURIComponent(exportId)}`;
}

// --------------------------------------------------------------------------
// Domain types — mirror the OpenAPI Delivery + Export schemas.
// --------------------------------------------------------------------------

/** Delivery — mirrors the openapi.yaml `Delivery` component schema. */
export interface Delivery {
  id: string;
  workspace_id: string;
  /** Lifecycle status — draft / approved / sent / accepted. */
  status: "draft" | "approved" | "sent" | "accepted" | string;
  approved_at?: string | null;
  sent_at?: string | null;
  artifact_urls?: string[];
  /** Optional UI-friendly summary the report renders verbatim. */
  summary?: DeliverySummary | null;
}

/** Optional embedded summary block (KPI tiles + bullet lists). */
export interface DeliverySummary {
  /** "Phase 1 納品レポート" 等のレポート種別ラベル. */
  title?: string | null;
  /** "受託 EC 構築 #4 / 基盤実装フェーズ" 等のサブタイトル. */
  subtitle?: string | null;
  delivery_id_label?: string | null;
  delivery_date?: string | null;
  client_email?: string | null;
  assignee_email?: string | null;
  /** 4 KPI tiles (完了タスク / Test PASS / Coverage / 赤線抵触). */
  kpi?: {
    completed_tasks?: number | null;
    tests_passed?: number | null;
    coverage_pct?: number | null;
    redline_breaches?: number | null;
  } | null;
  /** "2. 実装内容" 箇条書きの行. */
  implementation_items?: string[];
  /** "3. 検証結果" 表の行 (項目 / 結果 / 備考). */
  verification_rows?: VerificationRow[];
}

export interface VerificationRow {
  label: string;
  result: string;
  note?: string | null;
}

export interface WorkspaceDeliveryResponse {
  delivery: Delivery;
}

/** POST /api/workspaces/{id}/exports request body (AC-F2). */
export interface QueueExportRequest {
  type: "spec_pdf" | "delivery_report_pdf" | string;
}

/** POST /api/workspaces/{id}/exports response. */
export interface QueueExportResponse {
  export_id: string;
}

/** GET /api/exports/{id} response (AC-F3). */
export interface ExportRecord {
  id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  /**
   * Null while status is 'queued' or 'running' (AC-F3 contract). The UI keeps
   * the download button disabled until a non-null URL appears.
   */
  download_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

// --------------------------------------------------------------------------
// Error envelope (FastAPI {detail: {code, message}} contract).
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?:
    | string
    | {
        code?: string;
        message?: string;
        errors?: unknown;
      };
}

/** Thrown for any non-2xx response from a delivery / export endpoint. */
export class ExportsApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "ExportsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 / AC-F4: non-technical, end-user friendly message tagged with the
   * failing endpoint. Never embeds stack traces, SQL fragments, or raw
   * exception class names from the server.
   */
  toUserMessage(): string {
    const friendly =
      EXPORTS_USER_MESSAGES[this.status] ?? EXPORTS_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const EXPORTS_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "認証が無効です。再度ログインしてください",
  403: "この操作を実行する権限がありません",
  404: "納品レポートが見つかりませんでした",
  409: "現在この操作は実行できません",
  422: "入力内容を確認してください",
  429: "リクエストの上限に達しました。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "納品レポートの読み込みに失敗しました",
};

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

function resolveApiBase(apiBase?: string): string {
  if (apiBase) return apiBase;
  if (typeof process !== "undefined") {
    const env = process.env ?? {};
    if (env.NEXT_PUBLIC_API_URL) return env.NEXT_PUBLIC_API_URL;
    if (env.NEXT_PUBLIC_API_BASE) return env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

async function parseErrorEnvelope(
  response: Response,
  endpoint: string,
): Promise<ExportsApiError> {
  let code = "UNKNOWN_ERROR";
  let message = response.statusText || "request failed";
  try {
    const envelope = (await response.json()) as BackendErrorEnvelope;
    if (envelope && typeof envelope.detail === "object" && envelope.detail) {
      if (typeof envelope.detail.code === "string") code = envelope.detail.code;
      if (typeof envelope.detail.message === "string") {
        message = envelope.detail.message;
      }
    } else if (typeof envelope?.detail === "string") {
      message = envelope.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. We deliberately do not
    // embed the raw body to avoid leaking server stack traces (AC-F1 / F4).
  }
  return new ExportsApiError(code, message, response.status, endpoint);
}

export interface ExportsRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token forwarded as `Authorization: Bearer <token>`. */
  authToken?: string | null;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

function buildAuthHeader(
  opts: ExportsRequestOptions,
): Record<string, string> {
  if (!opts.authToken) return {};
  return { Authorization: `Bearer ${opts.authToken}` };
}

// --------------------------------------------------------------------------
// API functions
// --------------------------------------------------------------------------

/**
 * AC-F1: GET /api/workspaces/{id}/delivery via the typed client.
 *
 * Throws {@link ExportsApiError} on non-2xx — the error carries the failing
 * endpoint so the UI can surface a non-technical toast referencing it.
 */
export async function getWorkspaceDelivery(
  workspaceId: string,
  opts: ExportsRequestOptions = {},
): Promise<WorkspaceDeliveryResponse> {
  const endpoint = workspaceDeliveryEndpoint(workspaceId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        ...buildAuthHeader(opts),
      },
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ExportsApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as WorkspaceDeliveryResponse;
}

/**
 * AC-F2: POST /api/workspaces/{id}/exports with type=spec_pdf queues a PDF
 * generation job server-side and returns the new export_id. The backend is
 * required to respond within 1 second; the client does not enforce that here
 * (left to a server-side SLO / contract test).
 */
export async function requestSpecPdfExport(
  workspaceId: string,
  opts: ExportsRequestOptions = {},
): Promise<QueueExportResponse> {
  return queueExport(workspaceId, { type: "spec_pdf" }, opts);
}

/**
 * Lower-level helper — POST /api/workspaces/{id}/exports with an explicit
 * payload. The S-062 page only needs `type=spec_pdf` today, but the helper
 * stays open for the sibling S-061 page (T-V3-C-22) to reuse.
 */
export async function queueExport(
  workspaceId: string,
  body: QueueExportRequest,
  opts: ExportsRequestOptions = {},
): Promise<QueueExportResponse> {
  const endpoint = workspaceExportsEndpoint(workspaceId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...buildAuthHeader(opts),
      },
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ExportsApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as QueueExportResponse;
}

/**
 * AC-F3: GET /api/exports/{id} via the typed client. The backend returns
 * download_url=null while status is 'queued' or 'running'. The S-062 page polls
 * this endpoint after queueing a spec_pdf job and only enables the download
 * button once a non-null URL appears.
 */
export async function getExport(
  exportId: string,
  opts: ExportsRequestOptions = {},
): Promise<ExportRecord> {
  const endpoint = exportByIdEndpoint(exportId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        ...buildAuthHeader(opts),
      },
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ExportsApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as ExportRecord;
}
