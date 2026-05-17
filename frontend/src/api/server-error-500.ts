/**
 * T-V3-C-54 / S-045 — Typed client for the 500 server-error page.
 *
 * The S-045 screen is rendered as the top-level Next.js error boundary
 * (`frontend/src/app/global-error.tsx`) plus a regular route alias under
 * `frontend/src/app/(system)/server-error-500/page.tsx` so the URL
 * `/system/server-error-500` is reachable from the mock viewer and from
 * cross-screen links in the docs/mocks/.../index.html.
 *
 * Backend contract (read-only — error context only):
 *   GET /api/system/error-context?error_id=...  →
 *     { error_id, timestamp, path, status, support_url? }
 *
 *   The endpoint is best-effort: 200 returns a context envelope; 404 means
 *   the error_id is unknown (we still render the fallback shell); 401 means
 *   the user is not signed in and we must redirect to /login (AC-F1).
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1system~1error-context
 *
 * EARS AC mapping (T-V3-C-54):
 *   functional.AC-F1: UNWANTED unauthenticated visitor → 401 surfaces here so
 *                     the page can `router.replace("/login")` without leaking
 *                     workspace-scoped data.
 *   functional.AC-F2: STATE-DRIVEN data fetching — `getServerErrorContext` is
 *                     the boundary between fetch state and the page skeleton.
 *
 * Error envelope follows the project-wide FastAPI contract:
 *   { detail: { code: string; message: string } }
 */

import { env } from "@/env";

export const SERVER_ERROR_500_CONTEXT_ENDPOINT = "/api/system/error-context";

// --------------------------------------------------------------------------
// Wire types
// --------------------------------------------------------------------------

export interface ServerErrorContextResponse {
  /** Server-issued correlation id (mock: "err_a3f8c29b71"). */
  error_id: string;
  /** ISO-8601 timestamp the error was recorded at. */
  timestamp: string;
  /** Request path that produced the error (e.g. "POST /api/.../tasks"). */
  path: string;
  /** HTTP status (always 500 here, surfaced for display). */
  status: number;
  /** Optional support deep-link / mailto. */
  support_url?: string | null;
}

export interface ServerErrorContextRequest {
  /** Optional error_id surfaced by the React error boundary. */
  errorId?: string | null;
}

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/**
 * Thrown for any non-2xx response from `/api/system/error-context`.
 *
 * UNWANTED 401 detection (AC-F1) relies on `.status === 401`.
 */
export class ServerError500ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "ServerError500ApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  toUserMessage(): string {
    if (this.status === 401) return "サインインが必要です";
    if (this.status === 404) return "エラー詳細が見つかりませんでした";
    return "通信に失敗しました";
  }
}

// --------------------------------------------------------------------------
// Internal HTTP helper
// --------------------------------------------------------------------------

export interface ServerError500RequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: ServerError500RequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<ServerError500ApiError> {
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
    /* Non-JSON body — keep the synthesised message. */
  }
  return new ServerError500ApiError(code, message, response.status, endpoint);
}

/**
 * Fetch the optional server-side context for an error_id.
 *
 * Returns the envelope on 200, throws {@link ServerError500ApiError} on
 * non-2xx (the page handles 401 → redirect, every other status → fallback).
 */
export async function getServerErrorContext(
  req: ServerErrorContextRequest = {},
  opts: ServerError500RequestOptions = {},
): Promise<ServerErrorContextResponse> {
  const base = resolveApiBase(opts);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const qs = req.errorId
    ? `?error_id=${encodeURIComponent(req.errorId)}`
    : "";
  const url = `${base}${SERVER_ERROR_500_CONTEXT_ENDPOINT}${qs}`;

  const response = await fetchImpl(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "include",
    signal: opts.signal,
  });

  if (!response.ok) {
    throw await parseError(response, SERVER_ERROR_500_CONTEXT_ENDPOINT);
  }

  const body = (await response.json()) as ServerErrorContextResponse;
  return body;
}
