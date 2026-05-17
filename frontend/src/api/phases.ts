/**
 * T-V3-C-37 / F-008: Typed client for the workspace phases endpoints backing
 * the S-016 (フェーズ管理) screen.
 *
 * Backend contracts (T-V3-B-13 / drift T-V3-DRIFT-F-008-01..03):
 *   GET    /api/workspaces/{id}/phases                       (member)
 *   POST   /api/workspaces/{id}/phases                       (workspace_admin)
 *   POST   /api/workspaces/{id}/phases/{phase_id}/gate       (workspace_admin)
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *   #/paths/~1api~1workspaces~1{id}~1phases
 *   #/paths/~1api~1workspaces~1{id}~1phases~1{phase_id}~1gate
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by
 * the FastAPI backend. The thrown {@link PhasesApiError} surfaces a
 * non-technical message (with the failing endpoint tagged) for UI toasts,
 * never leaking server stack traces (AC-F1 on S-016 / T-V3-C-37).
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function workspacePhasesEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/phases`;
}

export function workspacePhaseGateEndpoint(
  workspaceId: string,
  phaseId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/phases/${encodeURIComponent(phaseId)}/gate`;
}

// --------------------------------------------------------------------------
// Types — narrow to what S-016 renders. Backend may include extra fields.
// --------------------------------------------------------------------------

/** A single phase row returned by GET /api/workspaces/{id}/phases. */
export interface Phase {
  id: string;
  name: string;
  /** "completed" | "running" | "locked" | "blocked" — kept open-ended. */
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  /** 0..100 percent complete. */
  progress?: number | null;
  /** Free-form gate conditions. The UI renders one row per condition. */
  gate_conditions?: PhaseGateCondition[] | null;
  /** Server may include task counts / arbitrary extras. */
  [extra: string]: unknown;
}

export interface PhaseGateCondition {
  /** Stable id when the backend supplies one (used as React key). */
  id?: string | null;
  label: string;
  /** true when satisfied; null/undefined treated as "pending". */
  satisfied?: boolean | null;
}

export interface GetPhasesResponse {
  phases: Phase[];
  current_phase_id?: string | null;
}

/** Payload for POST /api/workspaces/{id}/phases. */
export interface CreatePhasePayload {
  name: string;
  gate_conditions: string[];
}

export interface CreatePhaseResponse {
  phase_id: string;
  [extra: string]: unknown;
}

/** Payload for POST /api/workspaces/{id}/phases/{phase_id}/gate. */
export interface TriggerGatePayload {
  /** When true, force-unlock even if conditions are not all satisfied
   *  (workspace_admin override). */
  force?: boolean;
}

export interface TriggerGateResponse {
  unlocked_phase_id: string;
  evaluated_at: string;
  [extra: string]: unknown;
}

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象のフェーズが見つかりませんでした",
  409: "Gate 条件を満たしていません",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/** Thrown for any non-2xx response from the phases endpoints. */
export class PhasesApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(
    code: string,
    message: string,
    status: number,
    endpoint: string,
  ) {
    super(message);
    this.name = "PhasesApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-016 UNWANTED): produce a non-technical user-facing message that
   * references the failing endpoint without leaking server stack traces or
   * internal exception class names.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal HTTP helper
// --------------------------------------------------------------------------

export interface PhasesRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) required for authenticated role. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: PhasesRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<PhasesApiError> {
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
    // Non-JSON body — keep the synthesised message. AC-F1: don't leak raw body.
  }
  return new PhasesApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: PhasesRequestOptions,
): Promise<TOut> {
  const base = resolveApiBase(opts);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = `${base}${endpoint}`;

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (opts.authToken) {
    headers.Authorization = `Bearer ${opts.authToken}`;
  }

  let response: Response;
  try {
    response = await fetchImpl(url, {
      ...init,
      headers,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new PhasesApiError("NETWORK_ERROR", "network error", 0, endpoint);
  }

  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  if (response.status === 204) return {} as TOut;
  return (await response.json()) as TOut;
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

/**
 * GET /api/workspaces/{id}/phases — returns the workspace's ordered phases.
 *
 * AC-F1 surface: 4xx/5xx is normalised into a {@link PhasesApiError}.
 * Backend role: member (any workspace member may read).
 */
export function getPhases(
  workspaceId: string,
  opts: PhasesRequestOptions = {},
): Promise<GetPhasesResponse> {
  return request<GetPhasesResponse>(
    workspacePhasesEndpoint(workspaceId),
    { method: "GET" },
    opts,
  );
}

/**
 * POST /api/workspaces/{id}/phases — create a new phase with gate_conditions.
 *
 * Backend role: workspace_admin. The server enforces `max phases` (409 on
 * overflow); the UI just surfaces the endpoint-tagged user message via
 * {@link PhasesApiError.toUserMessage}.
 */
export function createPhase(
  workspaceId: string,
  body: CreatePhasePayload,
  opts: PhasesRequestOptions = {},
): Promise<CreatePhaseResponse> {
  return request<CreatePhaseResponse>(
    workspacePhasesEndpoint(workspaceId),
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/**
 * POST /api/workspaces/{id}/phases/{phase_id}/gate — evaluate the gate for a
 * phase. On success (all `gate_conditions` true on the server), the next
 * phase is unlocked and `unlocked_phase_id` is returned (AC-F3).
 *
 * Backend role: workspace_admin. 409 on "gate conditions not met".
 */
export function triggerPhaseGate(
  workspaceId: string,
  phaseId: string,
  body: TriggerGatePayload = {},
  opts: PhasesRequestOptions = {},
): Promise<TriggerGateResponse> {
  return request<TriggerGateResponse>(
    workspacePhaseGateEndpoint(workspaceId, phaseId),
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}
