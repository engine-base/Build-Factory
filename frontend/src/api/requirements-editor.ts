/**
 * T-V3-C-47 / F-006 (+ F-025): Typed client for the workspace requirements
 * editor (S-021 要件エディタ) backing the spec authoring screen.
 *
 * Backend contracts (T-V3-B-10 / merged via T-V3-B-006 + T-V3-B-025):
 *   GET    /api/workspaces/{id}/requirements
 *   PUT    /api/workspaces/{id}/requirements
 *   POST   /api/workspaces/{id}/requirements/versions
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1workspaces~1{id}~1requirements
 *
 * EARS AC mapping (逐語コピー from tickets-group-c-ui-part2.json#T-V3-C-47):
 *   functional.AC-F1: GET on mount; 2xx -> render; 4xx -> inline toast + empty state.
 *   functional.AC-F2: 401 -> redirect to /login (S-001); no workspace data renders.
 *   functional.AC-F3: PUT with EARS-conformant items persists and returns version+1.
 *   functional.AC-F4: every acceptance_criteria item must match one of the 5 EARS forms
 *                     BEFORE persisting (client-side validation guard).
 *
 * Errors follow the project-wide `{detail: {code, message}}` envelope. The
 * thrown {@link RequirementsApiError} surfaces a non-technical, endpoint-tagged
 * message for UI toasts and never leaks server stack traces.
 */

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function requirementsListEndpoint(workspaceId: string | number): string {
  return `/api/workspaces/${encodeURIComponent(String(workspaceId))}/requirements`;
}

export function requirementsPutEndpoint(workspaceId: string | number): string {
  return `/api/workspaces/${encodeURIComponent(String(workspaceId))}/requirements`;
}

export function requirementsVersionsEndpoint(
  workspaceId: string | number,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/requirements/versions`;
}

// --------------------------------------------------------------------------
// Domain types — mirror OpenAPI components/schemas (Requirement / RequirementItem).
// --------------------------------------------------------------------------

/** EARS notation forms (AC-F4 validator). Mirrors EARSCriterion.form. */
export const EARS_FORMS = [
  "UBIQUITOUS",
  "EVENT-DRIVEN",
  "STATE-DRIVEN",
  "OPTIONAL",
  "UNWANTED",
] as const;

export type EarsForm = (typeof EARS_FORMS)[number];

/** Lead phrase per EARS form used by {@link detectEarsForm}. */
const EARS_LEAD_PATTERNS: ReadonlyArray<{ form: EarsForm; pattern: RegExp }> = [
  // UNWANTED must beat plain "If" misclassifications — explicit "shall not".
  {
    form: "UNWANTED",
    pattern:
      /\bIf\b[\s\S]+?\b(?:the\s+system\s+shall\s+not|system\s+shall\s+not|shall\s+not)\b/i,
  },
  {
    form: "EVENT-DRIVEN",
    pattern: /\bWhen\b[\s\S]+?\b(?:the\s+system\s+shall|system\s+shall|shall)\b/i,
  },
  {
    form: "STATE-DRIVEN",
    pattern: /\bWhile\b[\s\S]+?\b(?:the\s+system\s+shall|system\s+shall|shall)\b/i,
  },
  {
    form: "OPTIONAL",
    pattern: /\bWhere\b[\s\S]+?\b(?:the\s+system\s+shall|system\s+shall|shall)\b/i,
  },
  // UBIQUITOUS is the default "shall" without a guard phrase — must run last.
  {
    form: "UBIQUITOUS",
    pattern: /^[^\n]*\b(?:the\s+system\s+shall|system\s+shall)\b/i,
  },
];

/**
 * Detect which EARS form a free-text acceptance_criteria item belongs to.
 * Returns `null` when the input does not match any of the 5 canonical forms.
 *
 * This is the AC-F4 (UBIQUITOUS) guard used by the page before PUT, so the
 * client never sends mal-formed AC items to the backend.
 */
export function detectEarsForm(text: string): EarsForm | null {
  if (typeof text !== "string") return null;
  const trimmed = text.trim();
  if (!trimmed) return null;
  for (const { form, pattern } of EARS_LEAD_PATTERNS) {
    if (pattern.test(trimmed)) return form;
  }
  return null;
}

/** Single requirement entry (mirrors RequirementItem / Requirement schema). */
export interface RequirementItem {
  id?: string | null;
  section: string;
  /** Markdown body containing EARS-formatted AC items. */
  body_md: string;
  /** Optional Must/Should/Could/Wont label per RequirementItem schema. */
  label?: "Must" | "Should" | "Could" | "Wont" | null;
  [extra: string]: unknown;
}

export interface RequirementsListResponse {
  requirements: RequirementItem[];
  /** Monotonic version counter — incremented on each successful PUT. */
  version: number;
  [extra: string]: unknown;
}

export interface RequirementsPutPayload {
  items: RequirementItem[];
}

export interface RequirementsPutResponse {
  /** Echo of the requirements document id. */
  id: string;
  /** Server-incremented version (version+1 vs the prior GET). */
  version: number;
  [extra: string]: unknown;
}

export interface RequirementsVersionCreatePayload {
  /** Optional label captured in the version log (e.g. "v2.1"). */
  label?: string | null;
  /** Optional commit-style message for the version history sidebar. */
  message?: string | null;
}

export interface RequirementsVersionCreateResponse {
  version_id: string;
  version_number: number;
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
  404: "要件ドキュメントが見つかりませんでした",
  409: "別のセッションが先に保存しました。再読み込みしてください",
  422: "EARS 形式に一致しない受け入れ条件があります",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the requirements endpoints. */
export class RequirementsApiError extends Error {
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
    this.name = "RequirementsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-021): produce a non-technical, user-facing message that references
   * the failing endpoint without leaking server stack traces (no traceback /
   * file paths / SQL ever embedded in the surfaced string).
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

/**
 * Thrown by {@link validateRequirementItems} when at least one AC line in the
 * supplied items does not match any of the 5 EARS forms.
 *
 * AC-F4 (UBIQUITOUS): every acceptance_criteria item must conform to EARS
 * before persisting — this error is raised client-side so the PUT never even
 * hits the wire on a known bad payload.
 */
export class EarsValidationError extends Error {
  readonly offending: Array<{ index: number; line: string }>;

  constructor(offending: Array<{ index: number; line: string }>) {
    super(
      `EARS 形式に一致しない受け入れ条件があります (${offending.length} 件)`,
    );
    this.name = "EarsValidationError";
    this.offending = offending;
  }
}

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

export interface RequirementsClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
  /** Test seam — overrides global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: RequirementsClientOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<RequirementsApiError> {
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
    // Non-JSON body — keep generic fallback. Never embed raw body to avoid
    // leaking server stack traces (AC-F1 non-technical).
  }
  return new RequirementsApiError(code, message, response.status, endpoint);
}

async function request<T>(
  method: "GET" | "POST" | "PUT",
  endpoint: string,
  body: unknown,
  opts: RequirementsClientOptions,
): Promise<T> {
  const base = resolveApiBase(opts);
  const url = `${base}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new RequirementsApiError(
      "requirements.network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) throw await parseError(response, endpoint);
  if (response.status === 204) return undefined as unknown as T;

  try {
    return (await response.json()) as T;
  } catch {
    return undefined as unknown as T;
  }
}

// --------------------------------------------------------------------------
// EARS client-side validation (AC-F4)
// --------------------------------------------------------------------------

/**
 * Extract AC-style lines from a Markdown body. Lines that look like a free-form
 * EARS sentence (i.e. start with one of the keywords or contain "shall") are
 * candidates; pure prose lines without any "shall" are ignored so AC-F4 only
 * fails on actual mal-formed AC entries.
 */
function extractAcLines(bodyMd: string): string[] {
  if (typeof bodyMd !== "string") return [];
  const lines = bodyMd.split(/\r?\n/);
  return lines
    .map((l) => l.trim())
    .filter((l) => {
      if (!l) return false;
      // Look at lines that intend to be AC: contain "shall" or start with an
      // EARS lead keyword. Prose without "shall" is body text, not an AC.
      if (/\bshall\b/i.test(l)) return true;
      return false;
    });
}

/**
 * AC-F4 (UBIQUITOUS): validate that every AC line across all items matches one
 * of the 5 EARS forms. Throws {@link EarsValidationError} on failure.
 *
 * The validator is intentionally tolerant of leading Markdown decoration
 * (e.g. "- **When** ..."), since the EARS lead phrase is what matters.
 */
export function validateRequirementItems(items: RequirementItem[]): void {
  if (!Array.isArray(items)) {
    throw new EarsValidationError([{ index: 0, line: "<not an array>" }]);
  }
  const offending: Array<{ index: number; line: string }> = [];
  items.forEach((item, idx) => {
    const lines = extractAcLines(item?.body_md ?? "");
    for (const line of lines) {
      // Strip leading Markdown bullets / numbering / bold markers before match.
      const normalised = line
        .replace(/^[-*+]\s+/, "")
        .replace(/^\d+\.\s+/, "")
        .replace(/\*\*/g, "")
        .trim();
      if (!detectEarsForm(normalised)) {
        offending.push({ index: idx, line });
      }
    }
  });
  if (offending.length > 0) throw new EarsValidationError(offending);
}

// --------------------------------------------------------------------------
// Typed API surface (S-021 AC-F1 / AC-F3)
// --------------------------------------------------------------------------

/** AC-F1 (S-021): GET /api/workspaces/{id}/requirements. */
export function getRequirements(
  workspaceId: string | number,
  opts: RequirementsClientOptions = {},
): Promise<RequirementsListResponse> {
  return request<RequirementsListResponse>(
    "GET",
    requirementsListEndpoint(workspaceId),
    undefined,
    opts,
  );
}

/**
 * AC-F3 (S-021): PUT /api/workspaces/{id}/requirements.
 *
 * Runs {@link validateRequirementItems} (AC-F4) before hitting the wire — the
 * EarsValidationError surfaces synchronously, so the page can render an inline
 * validation banner without bothering the server.
 */
export function putRequirements(
  workspaceId: string | number,
  payload: RequirementsPutPayload,
  opts: RequirementsClientOptions = {},
): Promise<RequirementsPutResponse> {
  validateRequirementItems(payload.items);
  return request<RequirementsPutResponse>(
    "PUT",
    requirementsPutEndpoint(workspaceId),
    payload,
    opts,
  );
}

/** POST /api/workspaces/{id}/requirements/versions — snapshot the current spec. */
export function createRequirementsVersion(
  workspaceId: string | number,
  payload: RequirementsVersionCreatePayload = {},
  opts: RequirementsClientOptions = {},
): Promise<RequirementsVersionCreateResponse> {
  return request<RequirementsVersionCreateResponse>(
    "POST",
    requirementsVersionsEndpoint(workspaceId),
    payload,
    opts,
  );
}
