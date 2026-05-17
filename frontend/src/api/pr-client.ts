/**
 * T-V3-C-15 / F-013 / S-042: Typed client for the public client-portal endpoints
 * backing the クライアントポータル screen.
 *
 * Backend contract (T-V3-B-20):
 *   GET  /api/client/workspaces/{token}        — backend/routers/client_portal.py::get_client_workspaces_by_token
 *   GET  /api/client/workspaces/{token}/spec   — backend/routers/client_portal.py::get_client_workspaces_by_token_spec
 *   POST /api/client/comments                  — backend/routers/client_portal.py::post_client_comments
 *   GET  /api/client/comments/{thread_id}      — backend/routers/client_portal.py::get_client_comments_by_thread_id
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/api/client/workspaces/{token}
 *          #/api/client/workspaces/{token}/spec
 *          #/api/client/comments
 *          #/api/client/comments/{thread_id}
 *
 * Auth model: PUBLIC (security: []) — the `token` path segment / body field is
 * the bearer of trust. No Authorization header is sent. The thrown
 * {@link ClientPortalApiError} surfaces a non-technical message tagged with
 * the failing endpoint, never leaking server stack traces (AC-F4 on S-042).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-15.md):
 *   functional.AC-F1 → `getClientWorkspace(token)` GETs the workspace overview.
 *   functional.AC-F2 → `getClientWorkspaceSpec(token)` GETs the spec link.
 *   functional.AC-F3 → `postClientComment({token, body, anchor?})` POSTs review comment.
 *   functional.AC-F4 → All 4xx/5xx → ClientPortalApiError.toUserMessage()
 *                      embeds the failing endpoint + a non-technical message
 *                      (no SQL / stack-trace / exception class).
 *   functional.AC-F5 → 409 on expired token surfaces as TokenExpiredError so
 *                      the page can render the dedicated "token expired" view.
 *   functional.AC-F6 → 429 rate-limit on POST surfaces a generic toast (the
 *                      backend enforces the 20/hour/token cap; the client
 *                      preserves the contract by mapping to a friendly message).
 */

// --------------------------------------------------------------------------
// Endpoint helpers (exposed so callers/tests can assert on canonical paths)
// --------------------------------------------------------------------------

export const CLIENT_WORKSPACE_ENDPOINT_PATTERN = "/api/client/workspaces/{token}";
export const CLIENT_SPEC_ENDPOINT_PATTERN = "/api/client/workspaces/{token}/spec";
export const CLIENT_COMMENTS_ENDPOINT = "/api/client/comments";
export const CLIENT_COMMENTS_THREAD_ENDPOINT_PATTERN =
  "/api/client/comments/{thread_id}";
export const COMMENTS_RESOLVE_ENDPOINT_PATTERN = "/api/comments/{id}/resolve";

/** Build the canonical workspace endpoint path for the given client token. */
export function clientWorkspaceEndpoint(token: string): string {
  return `/api/client/workspaces/${encodeURIComponent(token)}`;
}

/** Build the canonical workspace-spec endpoint path for the given client token. */
export function clientWorkspaceSpecEndpoint(token: string): string {
  return `/api/client/workspaces/${encodeURIComponent(token)}/spec`;
}

/** Build the canonical comments-by-thread endpoint path. */
export function clientCommentsThreadEndpoint(threadId: string): string {
  return `/api/client/comments/${encodeURIComponent(threadId)}`;
}

/** Build the canonical comment-resolve endpoint path (member-only). */
export function commentResolveEndpoint(commentId: string): string {
  return `/api/comments/${encodeURIComponent(commentId)}/resolve`;
}

// --------------------------------------------------------------------------
// Response types — mirror the OpenAPI schemas (PublicWorkspaceView, PublicComment)
// --------------------------------------------------------------------------

/** PublicWorkspaceView — minimal projection safe to expose without auth. */
export interface PublicWorkspaceView {
  /** Workspace id (UUID or numeric; treat opaque). */
  id: string | number;
  /** Display name. */
  name: string;
  /** Lifecycle status — running / review / archived. */
  status?: string | null;
  /** Current phase label (e.g. "Phase 2: 統合テスト + 受入"). */
  current_phase?: string | null;
  /** 0..1 phase progress ratio. */
  progress?: number | null;
  /** ISO-8601 timestamp of last public-visible update. */
  updated_at?: string | null;
  /** Optional KPI summary the portal hero block renders. */
  kpi?: Record<string, unknown> | null;
}

export interface ClientWorkspaceResponse {
  workspace: PublicWorkspaceView;
}

export interface ClientWorkspaceSpecResponse {
  /** Pre-rendered HTML URL (signed). */
  spec_html_url: string;
}

/** PublicComment — comment safe to expose via token. */
export interface PublicComment {
  id: string;
  thread_id?: string | null;
  body: string;
  anchor?: string | null;
  author_name?: string | null;
  created_at: string;
  resolved_at?: string | null;
}

export interface ClientCommentsResponse {
  comments: PublicComment[];
}

export interface PostClientCommentRequest {
  token: string;
  body: string;
  anchor?: string | null;
  thread_id?: string | null;
  author_name?: string | null;
}

export interface PostClientCommentResponse {
  comment_id: string;
}

// --------------------------------------------------------------------------
// Error envelope (FastAPI `{detail: {code, message}}` contract)
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

/** Thrown for any non-2xx response from a client-portal endpoint. */
export class ClientPortalApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "ClientPortalApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F4: non-technical, end-user friendly message tagged with the failing
   * endpoint. Never embeds stack traces / SQL / raw exception class names.
   */
  toUserMessage(): string {
    const friendly =
      CLIENT_PORTAL_USER_MESSAGES[this.status] ??
      CLIENT_PORTAL_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

/**
 * AC-F5 sentinel — backend returned 409 (TokenExpiredError per
 * client_portal.py::_service_error_to_http). The portal can use this to render
 * the dedicated "リンクの有効期限が切れました" page rather than a generic toast.
 */
export class TokenExpiredError extends ClientPortalApiError {
  constructor(endpoint: string, message = "token expired") {
    super("client_portal.token_expired", message, 409, endpoint);
    this.name = "TokenExpiredError";
  }
}

const CLIENT_PORTAL_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "リンクが無効です。発行元へお問い合わせください",
  403: "このリンクではこの操作を実行できません",
  404: "案件が見つかりませんでした",
  409: "リンクの有効期限が切れました。発行元へお問い合わせください",
  422: "入力内容を確認してください",
  429: "コメントの投稿数が上限に達しました。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "クライアントポータルの読み込みに失敗しました",
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
): Promise<ClientPortalApiError> {
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
    // intentionally ignore parse failure — keep generic fallback so we never
    // forward raw HTML / stack-traced JSON to the UI (AC-F4).
  }

  // AC-F5: 409 is the canonical "expired token" signal from the backend.
  if (response.status === 409) {
    return new TokenExpiredError(endpoint, message);
  }
  return new ClientPortalApiError(code, message, response.status, endpoint);
}

export interface ClientPortalRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

// --------------------------------------------------------------------------
// API functions
// --------------------------------------------------------------------------

/**
 * AC-F1: GET /api/client/workspaces/{token} via the typed client.
 *
 * Throws {@link ClientPortalApiError} on non-2xx (or {@link TokenExpiredError}
 * for the 409 expired-token case).
 */
export async function getClientWorkspace(
  token: string,
  opts: ClientPortalRequestOptions = {},
): Promise<ClientWorkspaceResponse> {
  const endpoint = clientWorkspaceEndpoint(token);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ClientPortalApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as ClientWorkspaceResponse;
}

/**
 * AC-F2: GET /api/client/workspaces/{token}/spec via the typed client.
 */
export async function getClientWorkspaceSpec(
  token: string,
  opts: ClientPortalRequestOptions = {},
): Promise<ClientWorkspaceSpecResponse> {
  const endpoint = clientWorkspaceSpecEndpoint(token);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ClientPortalApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as ClientWorkspaceSpecResponse;
}

/**
 * AC-F3: POST /api/client/comments via the typed client. Returns the new
 * comment id. Throws {@link ClientPortalApiError} on non-2xx; 429 surfaces as
 * the friendly "rate limited" message tagged with the endpoint (AC-F6).
 */
export async function postClientComment(
  body: PostClientCommentRequest,
  opts: ClientPortalRequestOptions = {},
): Promise<PostClientCommentResponse> {
  const endpoint = CLIENT_COMMENTS_ENDPOINT;
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
      },
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ClientPortalApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as PostClientCommentResponse;
}

/**
 * GET /api/client/comments/{thread_id} via the typed client. The S-042
 * overview page does not consume this directly today (review tab future work),
 * but it ships co-located so S-043 (T-V3-C-16) can reuse the same module.
 */
export async function getClientComments(
  threadId: string,
  token: string,
  opts: ClientPortalRequestOptions = {},
): Promise<ClientCommentsResponse> {
  const endpoint = clientCommentsThreadEndpoint(threadId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = new URL(`${baseUrl}${endpoint}`);
  url.searchParams.set("token", token);
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url.toString(), {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ClientPortalApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as ClientCommentsResponse;
}

/**
 * Response shape for `POST /api/comments/{id}/resolve`. The backend stamps
 * `resolved_at` server-side (see backend/services/client_portal_service.py
 * `resolve_comment`).
 */
export interface ResolveCommentResponse {
  id: string;
  resolved_at: string;
}

export interface ResolveCommentRequestOptions
  extends ClientPortalRequestOptions {
  /**
   * Optional session token forwarded as `Authorization: Bearer <token>`. The
   * resolve endpoint is **member-only** (require_user dependency) — when the
   * portal viewer is the public client, the backend returns 401 / 403 and the
   * S-043 page surfaces the friendly toast tagged with the failing endpoint.
   */
  authToken?: string | null;
}

/**
 * POST /api/comments/{id}/resolve via the typed client. Used by S-043 when a
 * workspace member chooses to resolve a comment thread. For the public client
 * viewer (no auth token), the backend returns 401 — caught and surfaced as a
 * non-technical toast tagged with the endpoint (AC-F4 on S-043).
 */
export async function resolveComment(
  commentId: string,
  opts: ResolveCommentRequestOptions = {},
): Promise<ResolveCommentResponse> {
  const endpoint = commentResolveEndpoint(commentId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (opts.authToken) {
    headers.Authorization = `Bearer ${opts.authToken}`;
  }

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers,
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ClientPortalApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as ResolveCommentResponse;
}
