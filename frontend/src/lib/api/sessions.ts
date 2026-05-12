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
