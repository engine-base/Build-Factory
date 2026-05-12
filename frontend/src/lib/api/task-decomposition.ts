// T-006-04: typed client for POST /api/task-decomposition/decompose.
//
// Spec: response shape matches backend/services/task_decomposition.py
//   {parent_brief, subtasks: [{title, acceptance_criteria: [{type, text}]}],
//    config: {backend_used, count_requested, count_returned}}
//
// Errors: backend returns {detail: {code, message}} for 4xx.

export const TASK_DECOMPOSITION_ENDPOINT = "/api/task-decomposition/decompose";

export type AcType =
  | "UBIQUITOUS"
  | "EVENT-DRIVEN"
  | "STATE-DRIVEN"
  | "OPTIONAL"
  | "UNWANTED";

export interface AcceptanceCriterion {
  type: AcType;
  text: string;
}

export interface Subtask {
  title: string;
  acceptance_criteria: AcceptanceCriterion[];
}

export interface DecomposeConfig {
  backend_used: boolean;
  count_requested: number;
  count_returned: number;
}

export interface DecomposeResponse {
  parent_brief: string;
  subtasks: Subtask[];
  config: DecomposeConfig;
}

export interface DecomposeRequest {
  parent_brief: string;
  subtask_count: number;
  use_backend?: boolean;
  actor_user_id?: string;
}

/**
 * Structured error from the backend matching {detail: {code, message}}.
 * AC-4 (UNWANTED) requires the UI to render code+message verbatim instead
 * of a generic "Error" string.
 */
export class TaskDecompositionError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "TaskDecompositionError";
    this.code = code;
    this.status = status;
  }
}

export interface DecomposeOptions {
  apiBase?: string;
  signal?: AbortSignal;
}

export async function decomposeTask(
  body: DecomposeRequest,
  opts: DecomposeOptions = {},
): Promise<DecomposeResponse> {
  const base =
    opts.apiBase ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8001";
  const resp = await fetch(`${base}${TASK_DECOMPOSITION_ENDPOINT}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: opts.signal,
  });

  if (!resp.ok) {
    let code = "task_decomposition.unknown";
    let message = `HTTP ${resp.status}`;
    try {
      const data = (await resp.json()) as {
        detail?: { code?: string; message?: string };
      };
      if (data?.detail?.code) code = data.detail.code;
      if (data?.detail?.message) message = data.detail.message;
    } catch {
      // ignore parse error; keep generic message
    }
    throw new TaskDecompositionError(code, message, resp.status);
  }

  return (await resp.json()) as DecomposeResponse;
}
