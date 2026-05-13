// T-010b-04: typed client for POST /api/agent/sessions (T-010b-01 endpoint REUSE).
//
// Request mirrors backend/routers/agent_runner.py CreateSessionRequest.
// Errors follow the project-wide {detail: {code, message}} contract.

export const AGENT_SESSIONS_ENDPOINT = "/api/agent/sessions";

export interface CreateSessionRequest {
  prompt: string;
  workspace_id?: number;
  project_id?: number;
  bf_task_id?: number;
  agent_persona?: string;
  skill_name?: string;
  model?: string; // default in backend = "claude-sonnet-4-6"
  sdk_session_id?: string;
  user_id?: string;
  run_in_background?: boolean; // default true
}

export interface CreateSessionResponse {
  session_id: number;
  status: string;
  // additional backend fields (e.g. created_at) preserved opaquely
  [key: string]: unknown;
}

export class AgentSessionError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "AgentSessionError";
    this.code = code;
    this.status = status;
  }
}

export interface CreateSessionOptions {
  apiBase?: string;
  signal?: AbortSignal;
}

export async function createAgentSession(
  body: CreateSessionRequest,
  opts: CreateSessionOptions = {},
): Promise<CreateSessionResponse> {
  const base =
    opts.apiBase ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8001";

  const payload: CreateSessionRequest = {
    run_in_background: true,
    model: "claude-sonnet-4-6",
    ...body,
  };

  const resp = await fetch(`${base}${AGENT_SESSIONS_ENDPOINT}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: opts.signal,
  });

  if (!resp.ok) {
    let code = "agent.unknown";
    let message = `HTTP ${resp.status}`;
    try {
      const data = (await resp.json()) as {
        detail?: { code?: string; message?: string };
      };
      if (data?.detail?.code) code = data.detail.code;
      if (data?.detail?.message) message = data.detail.message;
    } catch {
      // ignore parse error
    }
    throw new AgentSessionError(code, message, resp.status);
  }

  return (await resp.json()) as CreateSessionResponse;
}

// ────────────────────────────────────────────────────────────
// T-010d-03: SwarmSessionDetail UI 用 — GET session + log line 型 +
//             POST resume (4 choices)
// ────────────────────────────────────────────────────────────

export type SwarmSessionStatus = "running" | "done" | "crashed" | "paused";

export interface SwarmSessionData {
  id: number;
  status: SwarmSessionStatus | string;
  workspace_id?: number | null;
  bf_task_id?: number | null;
  agent_persona?: string | null;
  prompt?: string;
  crash_reason?: string | null;
  started_at?: number | null;
  completed_at?: number | null;
  // backend が追加する field は opaque で保持
  [key: string]: unknown;
}

export interface SwarmLogLine {
  /** epoch seconds or HH:MM:SS string. SwarmSessionDetail が format する. */
  time: number | string;
  /** plan / tool / status / stdout / error 等. */
  tool?: string;
  /** ログ本文. */
  status: string;
  /** PASS / FAIL / error 等 stdout カテゴリ. */
  kind?: "tool" | "status" | "error" | "stdout";
}

/** T-S0-08 VALID_RESUME_CHOICES と完全一致させる (cross-module invariant). */
export const VALID_RESUME_CHOICES = [
  "from_checkpoint",
  "rerun_full",
  "manual_fix",
  "cancel",
] as const;
export type ResumeChoice = (typeof VALID_RESUME_CHOICES)[number];

export async function fetchAgentSession(
  sessionId: number,
  opts: { apiBase?: string; signal?: AbortSignal } = {},
): Promise<SwarmSessionData> {
  const base =
    opts.apiBase ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8001";
  const resp = await fetch(`${base}${AGENT_SESSIONS_ENDPOINT}/${sessionId}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    signal: opts.signal,
  });
  if (!resp.ok) {
    let code = "agent.unknown";
    let message = `HTTP ${resp.status}`;
    try {
      const data = (await resp.json()) as {
        detail?: { code?: string; message?: string };
      };
      if (data?.detail?.code) code = data.detail.code;
      if (data?.detail?.message) message = data.detail.message;
    } catch {
      // ignore parse error
    }
    throw new AgentSessionError(code, message, resp.status);
  }
  return (await resp.json()) as SwarmSessionData;
}

export async function resumeAgentSession(
  sessionId: number,
  choice: ResumeChoice,
  opts: { apiBase?: string; signal?: AbortSignal } = {},
): Promise<{ session_id: number; status: string; resume_choice: ResumeChoice }> {
  if (!VALID_RESUME_CHOICES.includes(choice)) {
    throw new AgentSessionError(
      "agent.invalid_resume_choice",
      `choice must be one of ${VALID_RESUME_CHOICES.join(",")}`,
      400,
    );
  }
  const base =
    opts.apiBase ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8001";
  const resp = await fetch(
    `${base}${AGENT_SESSIONS_ENDPOINT}/${sessionId}/resume`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ choice }),
      signal: opts.signal,
    },
  );
  if (!resp.ok) {
    let code = "agent.unknown";
    let message = `HTTP ${resp.status}`;
    try {
      const data = (await resp.json()) as {
        detail?: { code?: string; message?: string };
      };
      if (data?.detail?.code) code = data.detail.code;
      if (data?.detail?.message) message = data.detail.message;
    } catch {
      // ignore parse error
    }
    throw new AgentSessionError(code, message, resp.status);
  }
  return (await resp.json()) as {
    session_id: number;
    status: string;
    resume_choice: ResumeChoice;
  };
}
