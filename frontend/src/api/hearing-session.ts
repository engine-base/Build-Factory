/**
 * T-V3-C-46 / S-020 / F-005 — Typed client for the hearing session endpoints.
 *
 * Backend contracts (T-V3-B-07 implemented):
 *   WS   /ws/hearing/{session_id}             — backend/routers/ws.py::ws_ws_hearing_by_session_id
 *   POST /api/workspaces/{id}/hearing/save    — backend/routers/workspaces.py::post_workspaces_by_id_hearing_save
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *   #/paths/~1ws~1hearing~1{session_id}
 *   #/paths/~1api~1workspaces~1{id}~1hearing~1save
 *
 * Errors follow the project-wide {detail: {code, message}} contract. The
 * thrown {@link HearingSessionApiError} surfaces a non-technical, endpoint
 * tagged message for UI toasts (AC-F1 / S-020) and never leaks server
 * stack traces or backend exception class names.
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function hearingWsEndpoint(sessionId: string): string {
  return `/ws/hearing/${encodeURIComponent(sessionId)}`;
}

export function hearingSaveEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/hearing/save`;
}

// --------------------------------------------------------------------------
// Wire types — mirror openapi.yaml and backend Pydantic models.
// --------------------------------------------------------------------------

/** A chat message streamed over WS /ws/hearing/{session_id}. */
export interface HearingChatMessage {
  /** Server-stable message id (uuid). */
  id: string;
  /** "ai" (mary / preston / secretary) | "user". */
  role: "ai" | "user";
  /** Optional persona name (e.g. "mary (BA)"). */
  author?: string | null;
  /** ISO-8601 timestamp. */
  created_at: string;
  /** Rendered message text (markdown allowed but rendered as plain text). */
  content: string;
}

/** Slot state for one of the 4 hearing steps (vision / target / features / constraints). */
export interface HearingSlotState {
  /** Slot key — "vision" | "target" | "features" | "constraints" | other. */
  key: string;
  /** Display label for the step indicator / sidebar. */
  label: string;
  /** "active" | "filled" | "pending". */
  status: "active" | "filled" | "pending";
  /** Free-form extracted text the AI has produced so far. */
  extracted?: string | null;
}

/** Stream events delivered over the WebSocket. */
export type HearingStreamEvent =
  | { type: "message"; message: HearingChatMessage }
  | { type: "slot_state"; slot: HearingSlotState }
  | { type: "typing"; author?: string | null }
  | { type: "end" }
  | { type: "error"; code: string; message: string };

/** POST /api/workspaces/{id}/hearing/save request payload. */
export interface HearingSaveRequest {
  /** Session id whose transcript / slots should be persisted. */
  session_id: string;
  /** Optional title for the resulting hearing artifact. */
  title?: string | null;
}

/** POST /api/workspaces/{id}/hearing/save 201 response. */
export interface HearingSaveResponse {
  hearing_id: string;
  saved_at: string;
}

// --------------------------------------------------------------------------
// Error class (AC-F1: 4xx surfaces non-leaky message)
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "入力内容を確認してください",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "ヒアリングセッションが見つかりませんでした",
  409: "ヒアリングの状態が一致しません",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/** Thrown for any non-2xx response from the hearing endpoints. */
export class HearingSessionApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "HearingSessionApiError";
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

export interface HearingSessionRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) — member role required. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: HearingSessionRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<HearingSessionApiError> {
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
  return new HearingSessionApiError(code, message, response.status, endpoint);
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

/**
 * POST /api/workspaces/{id}/hearing/save — persist the in-memory hearing
 * session as a permanent Hearing artifact. Returns the new hearing id and
 * the server-side save timestamp.
 */
export async function saveHearing(
  workspaceId: string,
  body: HearingSaveRequest,
  opts: HearingSessionRequestOptions = {},
): Promise<HearingSaveResponse> {
  const endpoint = hearingSaveEndpoint(workspaceId);
  const base = resolveApiBase(opts);
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (opts.authToken) {
    headers.Authorization = `Bearer ${opts.authToken}`;
  }

  let response: Response;
  try {
    response = await fetchImpl(`${base}${endpoint}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new HearingSessionApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  return (await response.json()) as HearingSaveResponse;
}

// --------------------------------------------------------------------------
// WebSocket helper (AC-F1 / AC-F3)
// --------------------------------------------------------------------------

export interface HearingWsOptions {
  /** Override the WS URL builder (jsdom tests inject `ws://localhost`). */
  apiBase?: string;
  /** Bearer token passed via `?token=` (browsers cannot set headers on WS). */
  authToken?: string | null;
  /** Test seam — defaults to global WebSocket. */
  webSocketImpl?: typeof WebSocket;
}

/** Compose the WS URL from the configured API base + session id. */
export function buildHearingWsUrl(
  sessionId: string,
  opts: HearingWsOptions = {},
): string {
  const baseHttp =
    opts.apiBase ?? env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
  const base = baseHttp.replace(/\/$/, "").replace(/^http/, "ws");
  const url = `${base}${hearingWsEndpoint(sessionId)}`;
  if (opts.authToken) {
    const sep = url.includes("?") ? "&" : "?";
    return `${url}${sep}token=${encodeURIComponent(opts.authToken)}`;
  }
  return url;
}

/** Parse a WS frame payload into a typed stream event; returns null on garbage. */
export function parseHearingStreamEvent(
  raw: string,
): HearingStreamEvent | null {
  try {
    const obj = JSON.parse(raw) as Partial<HearingStreamEvent> & {
      type?: string;
    };
    if (!obj || typeof obj.type !== "string") return null;
    switch (obj.type) {
      case "message":
      case "slot_state":
      case "typing":
      case "end":
      case "error":
        return obj as HearingStreamEvent;
      default:
        return null;
    }
  } catch {
    return null;
  }
}
