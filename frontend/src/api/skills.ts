/**
 * T-V3-C-14 / S-038 / F-002 / F-003: Typed client for the skills router.
 *
 * Backend contracts (T-V3-B-SKILLS-01 ほか実装済):
 *   GET    /api/skills                       — backend/routers/skills.py::get_skills
 *   POST   /api/skills                       — backend/routers/skills.py::post_skills
 *   POST   /api/skills/{id}/test             — backend/routers/skills.py::post_skills_by_id_test
 *   POST   /api/skills/{id}/archive          — backend/routers/skills.py::post_skills_by_id_archive
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1skills
 *
 * 4xx / 5xx は {detail: {code, message}} の FastAPI envelope を期待する。
 * SkillsApiError は AC-F5 (UNWANTED): non-technical message + failing endpoint
 * を持ち、サーバの stack trace / SQL / 内部パスを露出させないよう正規化する。
 */
import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoints
// --------------------------------------------------------------------------

export const SKILLS_LIST_ENDPOINT = "/api/skills";
export const SKILLS_CREATE_ENDPOINT = "/api/skills";
export const SKILLS_TEST_ENDPOINT_PATTERN = "/api/skills/{id}/test";
export const SKILLS_ARCHIVE_ENDPOINT_PATTERN = "/api/skills/{id}/archive";

// --------------------------------------------------------------------------
// Domain types — mirror openapi.yaml#/components/schemas/Skill (subset).
// --------------------------------------------------------------------------

/** Skill list item — fields the S-038 grid consumes. */
export interface Skill {
  /** Stable identifier (UUID v4 in v3; integer pk allowed for the bootstrap rows). */
  id: string | number;
  /** Slug-style name (alphanum + hyphen). */
  name: string;
  /** Optional display label rendered in the grid card title. */
  display_name?: string;
  /** Human description shown under the title (truncated by the UI). */
  description?: string | null;
  /** spec / impl / review / ops / general — surfaced as the bottom-left chip. */
  category: string;
  /** Semantic version string ("v 1.0" rendered in mock). */
  version?: string;
  /** Soft-archive timestamp (ISO-8601). null/undefined = active. */
  archived_at?: string | null;
  /** Comma-separated tag list (legacy bootstrap field). */
  tags?: string | null;
  /** Bootstrap-era usage counter ("87 uses" in mock). */
  usage_count?: number;
  /** ISO-8601 timestamp last invoked / edited. */
  updated_at?: string;
}

export interface ListSkillsResponse {
  items: Skill[];
  total: number;
}

export interface ListSkillsQuery {
  /** Filter by openapi.yaml `category` query parameter. */
  category?: string;
  /** When true, includes soft-archived rows (default backend behaviour: false). */
  archived?: boolean;
}

export interface CreateSkillRequest {
  /** 1..128 chars, slug-style. */
  name: string;
  /** spec / impl / review / ops / general. */
  category: string;
  /** Human description (1..2048 chars). */
  description: string;
  /** Raw SKILL.md body. */
  skill_md: string;
}

export interface CreateSkillResponse {
  id: string;
  name: string;
}

export interface TestSkillRequest {
  /** Free-form test prompt forwarded to the skill runner. */
  test_input: string;
}

export interface TestSkillResponse {
  /** Skill runner output (markdown / plaintext). */
  output: string;
  /** Wall-clock duration of the test invocation. */
  duration_ms: number;
}

export interface ArchiveSkillResponse {
  /** ISO-8601 timestamp the row was soft-archived at. */
  archived_at: string;
}

// --------------------------------------------------------------------------
// Error class (AC-F5)
// --------------------------------------------------------------------------

/** Backend FastAPI error envelope: `{detail: {code, message, errors?}}`. */
interface BackendErrorEnvelope {
  detail?:
    | {
        code?: string;
        message?: string;
        errors?: unknown;
      }
    | string;
}

/** Thrown for any non-2xx response from the skills router. */
export class SkillsApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "SkillsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F5 (UNWANTED): produce a non-technical user-facing message that
   * references the failing endpoint without leaking server stack traces.
   *
   * Output shape: `"GET /api/skills: <短文>"` — endpoint は必ず含み、
   * 内部 stack / SQL / file path / Exception 文字列は混入させない。
   */
  toUserMessage(): string {
    const friendly = SKILL_USER_MESSAGES[this.status] ?? SKILL_USER_MESSAGES.default;
    return `${this.endpoint}: ${friendly}`;
  }
}

const SKILL_USER_MESSAGES: Record<number | "default", string> = {
  400: "入力内容を確認してください",
  401: "サインインが必要です",
  403: "この操作を行う権限がありません",
  404: "対象のスキルが見つかりません",
  409: "既にアーカイブされているスキルです",
  422: "入力内容を確認してください",
  429: "テスト実行の上限に達しました。1 分待ってから再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  502: "サーバーで一時的なエラーが発生しました",
  503: "サーバーで一時的なエラーが発生しました",
  504: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました。時間をおいて再試行してください",
};

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

interface RequestOptions {
  fetchImpl?: typeof fetch;
  baseUrl?: string;
  signal?: AbortSignal;
  /** Bearer token for `Authorization: Bearer ...` (optional; defaults to localStorage). */
  accessToken?: string | null;
}

function resolveBaseUrl(opts?: RequestOptions): string {
  return opts?.baseUrl ?? env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
}

function resolveFetch(opts?: RequestOptions): typeof fetch {
  return opts?.fetchImpl ?? fetch;
}

function resolveAccessToken(opts?: RequestOptions): string | null {
  if (opts && "accessToken" in opts) {
    return opts.accessToken ?? null;
  }
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("bf.access_token");
  } catch {
    return null;
  }
}

function buildAuthHeaders(token: string | null): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function parseErrorEnvelope(
  res: Response,
): Promise<{ code: string; message?: string }> {
  let body: BackendErrorEnvelope | null = null;
  try {
    body = (await res.json()) as BackendErrorEnvelope;
  } catch {
    body = null;
  }
  if (body && typeof body === "object" && body.detail) {
    if (typeof body.detail === "string") {
      return { code: defaultCodeFor(res.status), message: body.detail };
    }
    return {
      code: body.detail.code ?? defaultCodeFor(res.status),
      message: body.detail.message,
    };
  }
  return { code: defaultCodeFor(res.status) };
}

function defaultCodeFor(status: number): string {
  if (status === 401) return "UNAUTHORIZED";
  if (status === 403) return "FORBIDDEN";
  if (status === 404) return "NOT_FOUND";
  if (status === 409) return "CONFLICT";
  if (status === 422) return "VALIDATION_ERROR";
  if (status === 429) return "RATE_LIMITED";
  if (status >= 500) return "INTERNAL_SERVER_ERROR";
  return "REQUEST_FAILED";
}

function buildListQuery(query?: ListSkillsQuery): string {
  if (!query) return "";
  const params = new URLSearchParams();
  if (query.category !== undefined) params.set("category", query.category);
  if (query.archived !== undefined) {
    params.set("archived", query.archived ? "true" : "false");
  }
  const q = params.toString();
  return q ? `?${q}` : "";
}

// --------------------------------------------------------------------------
// Public API (typed)
// --------------------------------------------------------------------------

/**
 * AC-F1: GET /api/skills.
 *
 * EVENT-DRIVEN: When the S-038 page mounts (and when filters change),
 * the system shall call GET /api/skills via this typed client.
 *
 * @throws {SkillsApiError} on 4xx / 5xx / network failure (AC-F5).
 */
export async function listSkills(
  query?: ListSkillsQuery,
  opts?: RequestOptions,
): Promise<ListSkillsResponse> {
  const endpoint = `GET ${SKILLS_LIST_ENDPOINT}`;
  const url = `${resolveBaseUrl(opts)}${SKILLS_LIST_ENDPOINT}${buildListQuery(query)}`;
  const token = resolveAccessToken(opts);

  let res: Response;
  try {
    res = await resolveFetch(opts)(url, {
      method: "GET",
      headers: buildAuthHeaders(token),
      signal: opts?.signal,
    });
  } catch {
    throw new SkillsApiError(
      "NETWORK_ERROR",
      "network unreachable",
      0,
      endpoint,
    );
  }

  if (!res.ok) {
    const { code, message } = await parseErrorEnvelope(res);
    throw new SkillsApiError(code, message ?? "request failed", res.status, endpoint);
  }

  // Backend may return either {items, total} (openapi v3) or a bare array
  // (legacy bootstrap router) — normalise to {items, total}.
  const data: unknown = await res.json().catch(() => null);
  if (Array.isArray(data)) {
    return { items: data as Skill[], total: data.length };
  }
  if (data && typeof data === "object" && Array.isArray((data as ListSkillsResponse).items)) {
    const items = (data as ListSkillsResponse).items;
    const total = (data as ListSkillsResponse).total ?? items.length;
    return { items, total };
  }
  return { items: [], total: 0 };
}

/**
 * AC-F2: POST /api/skills.
 *
 * EVENT-DRIVEN: When the S-038 page submits the "新規スキル作成" modal,
 * the system shall call POST /api/skills via this typed client.
 *
 * AC-F8 (UNWANTED): non-owner roles surface as `SkillsApiError(status=403)`.
 *
 * @throws {SkillsApiError} on 4xx / 5xx / network failure.
 */
export async function createSkill(
  body: CreateSkillRequest,
  opts?: RequestOptions,
): Promise<CreateSkillResponse> {
  const endpoint = `POST ${SKILLS_CREATE_ENDPOINT}`;
  const url = `${resolveBaseUrl(opts)}${SKILLS_CREATE_ENDPOINT}`;
  const token = resolveAccessToken(opts);

  let res: Response;
  try {
    res = await resolveFetch(opts)(url, {
      method: "POST",
      headers: buildAuthHeaders(token),
      body: JSON.stringify(body),
      signal: opts?.signal,
    });
  } catch {
    throw new SkillsApiError(
      "NETWORK_ERROR",
      "network unreachable",
      0,
      endpoint,
    );
  }

  if (!res.ok) {
    const { code, message } = await parseErrorEnvelope(res);
    throw new SkillsApiError(code, message ?? "request failed", res.status, endpoint);
  }

  const data = (await res.json().catch(() => ({}))) as CreateSkillResponse;
  return {
    id: data.id ?? "",
    name: data.name ?? body.name,
  };
}

/**
 * AC-F3: POST /api/skills/{id}/test.
 *
 * EVENT-DRIVEN: When the user invokes "テスト実行" from the S-038 page,
 * the system shall call POST /api/skills/{id}/test via this typed client.
 *
 * AC-F9 (UNWANTED): >10 calls/min/user surfaces as `SkillsApiError(status=429)`.
 *
 * @throws {SkillsApiError} on 4xx / 5xx / network failure.
 */
export async function testSkill(
  id: string | number,
  body: TestSkillRequest,
  opts?: RequestOptions,
): Promise<TestSkillResponse> {
  const path = `/api/skills/${encodeURIComponent(String(id))}/test`;
  const endpoint = `POST ${SKILLS_TEST_ENDPOINT_PATTERN}`;
  const url = `${resolveBaseUrl(opts)}${path}`;
  const token = resolveAccessToken(opts);

  let res: Response;
  try {
    res = await resolveFetch(opts)(url, {
      method: "POST",
      headers: buildAuthHeaders(token),
      body: JSON.stringify(body),
      signal: opts?.signal,
    });
  } catch {
    throw new SkillsApiError(
      "NETWORK_ERROR",
      "network unreachable",
      0,
      endpoint,
    );
  }

  if (!res.ok) {
    const { code, message } = await parseErrorEnvelope(res);
    throw new SkillsApiError(code, message ?? "request failed", res.status, endpoint);
  }

  const data = (await res.json().catch(() => ({}))) as TestSkillResponse;
  return {
    output: data.output ?? "",
    duration_ms: data.duration_ms ?? 0,
  };
}

/**
 * AC-F4 / AC-F7: POST /api/skills/{id}/archive.
 *
 * EVENT-DRIVEN: When the user clicks the archive icon on an S-038 card,
 * the system shall call POST /api/skills/{id}/archive via this typed client.
 *
 * @throws {SkillsApiError} on 4xx / 5xx / network failure.
 */
export async function archiveSkill(
  id: string | number,
  opts?: RequestOptions,
): Promise<ArchiveSkillResponse> {
  const path = `/api/skills/${encodeURIComponent(String(id))}/archive`;
  const endpoint = `POST ${SKILLS_ARCHIVE_ENDPOINT_PATTERN}`;
  const url = `${resolveBaseUrl(opts)}${path}`;
  const token = resolveAccessToken(opts);

  let res: Response;
  try {
    res = await resolveFetch(opts)(url, {
      method: "POST",
      headers: buildAuthHeaders(token),
      signal: opts?.signal,
    });
  } catch {
    throw new SkillsApiError(
      "NETWORK_ERROR",
      "network unreachable",
      0,
      endpoint,
    );
  }

  if (!res.ok) {
    const { code, message } = await parseErrorEnvelope(res);
    throw new SkillsApiError(code, message ?? "request failed", res.status, endpoint);
  }

  const data = (await res.json().catch(() => ({}))) as ArchiveSkillResponse;
  return { archived_at: data.archived_at ?? new Date().toISOString() };
}
