/**
 * T-V3-C-44 / F-013 / S-033: Typed client for the workspace PR-review endpoints
 * backing the PR レビュー screen.
 *
 * Backend contract (T-V3-B-19 / backend/routers/pr_review.py):
 *   GET  /api/workspaces/{id}/prs/{pr_number}  — get_workspaces_by_id_prs_by_pr_number
 *   POST /api/prs/{id}/approve                 — post_prs_by_id_approve
 *   POST /api/prs/{id}/comments                — post_prs_by_id_comments
 *   POST /api/prs/{id}/merge                   — post_prs_by_id_merge
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/api/workspaces/{id}/prs/{pr_number}
 *          #/api/prs/{id}/approve
 *          #/api/prs/{id}/comments
 *          #/api/prs/{id}/merge
 *
 * Auth model: bearerAuth (workspace member; merge / approve require
 * workspace_admin role server-side per features.json#F-013).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-44.md):
 *   functional.AC-F1 → getWorkspacePr(workspaceId, prNumber) GETs the PR payload.
 *   functional.AC-F2 → 4xx / 401 surfaces as PrReviewApiError so the page can
 *                      route unauthenticated callers to /login (S-001) and
 *                      render an inline error toast + empty state on other 4xx.
 *   functional.AC-F3 → mergePr({prId, mergeMethod}) POSTs the merge to GitHub
 *                      via the backend; server emits the pr_merged audit log.
 *
 * The client follows the project-wide FastAPI {detail: {code, message}} envelope
 * and never forwards a raw stack trace to the UI.
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint helpers — exposed so callers/tests can assert on canonical paths.
// --------------------------------------------------------------------------

export const PR_GET_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/prs/{pr_number}";
export const PR_APPROVE_ENDPOINT_PATTERN = "/api/prs/{id}/approve";
export const PR_COMMENTS_ENDPOINT_PATTERN = "/api/prs/{id}/comments";
export const PR_MERGE_ENDPOINT_PATTERN = "/api/prs/{id}/merge";

/** Build the canonical workspace-PR endpoint path. */
export function workspacePrEndpoint(
  workspaceId: number | string,
  prNumber: number | string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/prs/${encodeURIComponent(String(prNumber))}`;
}

/** Build the canonical PR-approve endpoint path. */
export function prApproveEndpoint(prId: number | string): string {
  return `/api/prs/${encodeURIComponent(String(prId))}/approve`;
}

/** Build the canonical PR-comments endpoint path. */
export function prCommentsEndpoint(prId: number | string): string {
  return `/api/prs/${encodeURIComponent(String(prId))}/comments`;
}

/** Build the canonical PR-merge endpoint path. */
export function prMergeEndpoint(prId: number | string): string {
  return `/api/prs/${encodeURIComponent(String(prId))}/merge`;
}

// --------------------------------------------------------------------------
// Wire types — mirror backend/services/pr_service.py + openapi.yaml.
// --------------------------------------------------------------------------

/** Minimal PR projection — matches the backend pr_service response. */
export interface PullRequestView {
  id: number | string;
  pr_number?: number | null;
  title?: string | null;
  body?: string | null;
  state?: string | null;
  base_branch?: string | null;
  head_branch?: string | null;
  author?: string | null;
  author_name?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  merged_at?: string | null;
  approved_at?: string | null;
  workspace_id?: number | string | null;
  /** Pre-rendered HTML review artifact URL (set after T-013-03 runs). */
  html_review_url?: string | null;
  /** AI reviewer summary text (Markdown / plain). */
  ai_review_summary?: string | null;
}

/** Inline / threaded PR comment. */
export interface PrComment {
  id: string | number;
  body: string;
  anchor_file?: string | null;
  anchor_line?: number | null;
  author?: string | null;
  author_name?: string | null;
  created_at?: string | null;
}

/** Single file changed in the diff. */
export interface PrFileChange {
  filename: string;
  status?: string | null;
  additions?: number | null;
  deletions?: number | null;
  patch?: string | null;
}

/** GET /api/workspaces/{id}/prs/{pr_number} response (T-V3-B-19). */
export interface WorkspacePrResponse {
  pr: PullRequestView;
  comments?: PrComment[];
  files?: PrFileChange[];
  /** Aggregate CI / lint check status (e.g. {passed: 19, failed: 0}). */
  checks?: Record<string, unknown> | null;
}

export interface ApprovePrRequest {
  /** Optional approval comment (free text, <= 2000 chars). */
  comment?: string | null;
}

export interface ApprovePrResponse {
  approved_at: string;
}

export interface PostPrCommentRequest {
  body: string;
  anchor_file?: string | null;
  anchor_line?: number | null;
}

export interface PostPrCommentResponse {
  comment_id: string;
}

/** Merge methods supported by the backend (see VALID_MERGE_METHODS). */
export type PrMergeMethod = "merge" | "squash" | "rebase";

export interface MergePrRequest {
  merge_method: PrMergeMethod;
}

export interface MergePrResponse {
  merged_at: string;
  sha?: string | null;
}

// --------------------------------------------------------------------------
// Error envelope — matches the project-wide FastAPI contract.
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

/** Thrown for any non-2xx response from a PR-review endpoint. */
export class PrReviewApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "PrReviewApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * Non-technical, end-user friendly message tagged with the failing endpoint.
   * Never embeds stack traces / SQL / raw exception class names (AC-F2 / F4).
   */
  toUserMessage(): string {
    const friendly =
      PR_REVIEW_USER_MESSAGES[this.status] ??
      PR_REVIEW_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const PR_REVIEW_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "ログインが必要です",
  403: "この操作を実行する権限がありません",
  404: "PR が見つかりませんでした",
  409: "既に処理済みです",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "PR の読み込みに失敗しました",
};

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

function resolveApiBase(apiBase?: string): string {
  if (apiBase) return apiBase;
  // env may not be available in test environments; fall back to localhost.
  const fromEnv =
    (typeof process !== "undefined" &&
      (process.env?.NEXT_PUBLIC_API_URL ??
        process.env?.NEXT_PUBLIC_API_BASE)) ||
    undefined;
  if (fromEnv) return fromEnv;
  try {
    if (env?.NEXT_PUBLIC_API_URL) return env.NEXT_PUBLIC_API_URL;
  } catch {
    /* swallow — env is not always defined in test contexts */
  }
  return "http://localhost:8001";
}

async function parseErrorEnvelope(
  response: Response,
  endpoint: string,
): Promise<PrReviewApiError> {
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
    // intentionally ignore parse failure — keep the generic fallback so we
    // never forward raw HTML / stack-traced JSON to the UI (AC-F2 / F4).
  }
  return new PrReviewApiError(code, message, response.status, endpoint);
}

export interface PrReviewRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Optional bearer token forwarded as `Authorization: Bearer <token>`. */
  authToken?: string | null;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

function buildHeaders(
  opts: PrReviewRequestOptions,
  hasJsonBody: boolean,
): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (hasJsonBody) headers["Content-Type"] = "application/json";
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;
  return headers;
}

// --------------------------------------------------------------------------
// API functions
// --------------------------------------------------------------------------

/**
 * AC-F1: GET /api/workspaces/{id}/prs/{pr_number} via the typed client.
 *
 * Throws {@link PrReviewApiError} on non-2xx so the page can:
 *  - redirect to /login (S-001) on 401 (AC-F2)
 *  - render the inline error toast + empty state on other 4xx (AC-F2 tail).
 */
export async function getWorkspacePr(
  workspaceId: number | string,
  prNumber: number | string,
  opts: PrReviewRequestOptions = {},
): Promise<WorkspacePrResponse> {
  const endpoint = workspacePrEndpoint(workspaceId, prNumber);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: buildHeaders(opts, false),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new PrReviewApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as WorkspacePrResponse;
}

/** POST /api/prs/{id}/approve via the typed client (workspace_admin only). */
export async function approvePr(
  prId: number | string,
  body: ApprovePrRequest = {},
  opts: PrReviewRequestOptions = {},
): Promise<ApprovePrResponse> {
  const endpoint = prApproveEndpoint(prId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: buildHeaders(opts, true),
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new PrReviewApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as ApprovePrResponse;
}

/** POST /api/prs/{id}/comments via the typed client (member+). */
export async function postPrComment(
  prId: number | string,
  body: PostPrCommentRequest,
  opts: PrReviewRequestOptions = {},
): Promise<PostPrCommentResponse> {
  const endpoint = prCommentsEndpoint(prId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: buildHeaders(opts, true),
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new PrReviewApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as PostPrCommentResponse;
}

/**
 * AC-F3: POST /api/prs/{id}/merge via the typed client.
 *
 * Server emits the `pr_merged` audit log and returns the merge commit sha.
 * Requires workspace_admin (server-enforced); on 403 the page surfaces a
 * friendly toast tagged with the failing endpoint.
 */
export async function mergePr(
  prId: number | string,
  body: MergePrRequest,
  opts: PrReviewRequestOptions = {},
): Promise<MergePrResponse> {
  const endpoint = prMergeEndpoint(prId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: buildHeaders(opts, true),
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new PrReviewApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as MergePrResponse;
}
