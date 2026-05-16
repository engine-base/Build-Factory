/**
 * T-V3-C-11 / F-024: Typed client for GET /api/search (Global Search Cmd+K).
 *
 * Backend contract: backend/routers/search.py::search (T-V3-B-27 / T-V3-B-SEARCH-01).
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/api/search
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by the
 * FastAPI backend. The thrown SearchApiError surfaces a non-technical message
 * for the UI toast while preserving the failing endpoint reference, never
 * leaking server stack traces (AC-F2).
 */
import type { ReadonlyURLSearchParams } from "next/navigation";

export const SEARCH_ENDPOINT = "/api/search";

/** Search hit kind — must stay in sync with openapi.yaml#/components/schemas/SearchHit.kind. */
export const SEARCH_HIT_KINDS = [
  "workspace",
  "task",
  "spec",
  "mock",
  "ai_employee",
  "skill",
  "audit_log",
] as const;
export type SearchHitKind = (typeof SEARCH_HIT_KINDS)[number];

/** Categories accepted by GET /api/search?category=. */
export const SEARCH_CATEGORIES = [
  "tasks",
  "artifacts",
  "knowledge",
  "audit",
] as const;
export type SearchCategory = (typeof SEARCH_CATEGORIES)[number];

export interface SearchHit {
  /** Stable id of the underlying resource (uuid / numeric / route key). */
  id: string;
  /** Resource type — drives icon + group heading on S-011. */
  kind: SearchHitKind | string;
  /** Display title shown on the first line of the hit row. */
  title: string;
  /** Optional excerpt (FTS / vector snippet). */
  snippet?: string;
  /** Deep-link URL the UI navigates to on Enter. */
  url?: string;
  /** Combined FTS + vector ranking score (AC-F3, openapi `score`). */
  score?: number;
}

export interface SearchResponse {
  hits: SearchHit[];
  total: number;
  /** Backend returns a `{category: count}` map but openapi descriptor allows any object. */
  categories?: Record<string, number> | unknown;
  /** Echoes back the normalized query (backend lower-cased / trimmed). */
  query?: string;
  /** Remaining tokens in the 60 req/min rate-limit window. */
  rate_limit_remaining?: number;
}

/** Thrown for any non-2xx response from GET /api/search. */
export class SearchApiError extends Error {
  code: string;
  status: number;
  endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "SearchApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F2: produce a non-technical user-facing message that references the
   * failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly =
      SEARCH_USER_MESSAGES[this.status] ?? SEARCH_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const SEARCH_USER_MESSAGES: Record<number | "default", string> = {
  400: "検索クエリが不正です",
  401: "サインインが必要です",
  403: "この検索を実行する権限がありません",
  422: "検索条件を確認してください",
  429: "検索回数の上限に達しました。しばらく待って再試行してください",
  500: "検索に失敗しました。時間をおいて再試行してください",
  default: "検索に失敗しました",
};

function resolveApiBase(opts: { apiBase?: string }): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

export interface SearchOptions {
  query: string;
  category?: SearchCategory | string | null;
  limit?: number;
  apiBase?: string;
  signal?: AbortSignal;
}

/**
 * AC-F1: GET /api/search?q={query}&category={cat} via the typed API client.
 *
 * Returns the raw SearchResponse on 2xx. Throws SearchApiError otherwise so
 * the caller can decide how to surface AC-F2 toasts.
 */
export async function searchGlobal(
  opts: SearchOptions,
): Promise<SearchResponse> {
  const base = resolveApiBase(opts);
  const params = new URLSearchParams({ q: opts.query });
  if (opts.category) params.set("category", String(opts.category));
  if (typeof opts.limit === "number") params.set("limit", String(opts.limit));

  const url = `${base}${SEARCH_ENDPOINT}?${params.toString()}`;
  const endpointLabel = `${SEARCH_ENDPOINT}?q=…`;

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
    throw new SearchApiError(
      "search.network_error",
      "network error",
      0,
      endpointLabel,
    );
  }

  if (!resp.ok) {
    let code = "search.unknown";
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
    throw new SearchApiError(code, message, resp.status, endpointLabel);
  }

  return (await resp.json()) as SearchResponse;
}

/** Helper for tests / URL deep-links: build the same querystring used by `searchGlobal`. */
export function buildSearchSearchParams(
  query: string,
  category?: SearchCategory | string | null,
): URLSearchParams {
  const params = new URLSearchParams({ q: query });
  if (category) params.set("category", String(category));
  return params;
}

/** Reverse of `buildSearchSearchParams`: read query + category from app router params. */
export function parseSearchSearchParams(
  searchParams: URLSearchParams | ReadonlyURLSearchParams,
): { query: string; category: string | null } {
  return {
    query: searchParams.get("q") ?? "",
    category: searchParams.get("category"),
  };
}
