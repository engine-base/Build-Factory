"use client";

// T-010b-04: Play ボタン + session 起動 (existing POST /api/agent/sessions REUSE).
//
// AC-1 UBIQUITOUS: shadcn Button + Lucide Play icon. 絵文字禁止 (CLAUDE.md §5.1).
// AC-2 EVENT-DRIVEN: クリックで POST. run_in_background=true で即時 session_id 返却.
//                     loading 中は Loader2 spinner. error は code+message 表示.
// AC-3 STATE-DRIVEN: button は loading 中 disabled. onStarted / onError 以外
//                     global state を mutate しない.
// AC-4 UNWANTED: prompt 空 → disabled / 4xx → code+message verbatim /
//                 BLACK RIGHT-POINTING TRIANGLE (U+25B6) emoji 禁止 /
//                 禁止 icon lib (@heroicons / @fortawesome / react-icons) 不使用.

import * as React from "react";
import { Loader2, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import {
  AgentSessionError,
  createAgentSession,
  type CreateSessionRequest,
  type CreateSessionResponse,
} from "@/lib/api/sessions";

export interface PlaySessionButtonProps {
  /** Required prompt to launch the agent session. */
  prompt: string;
  /** Optional context propagated to the backend (workspace/project/task). */
  workspace_id?: number;
  project_id?: number;
  bf_task_id?: number;
  /** BMAD persona (mary / devon / quinn / etc). */
  agent_persona?: string;
  /** Optional model override (default claude-sonnet-4-6 inside the client). */
  model?: string;
  /** Optional skill name passed to the SDK runner. */
  skill_name?: string;
  /** Audit-log actor id; backend 401 if empty string is sent. */
  user_id?: string;
  /** Optional override (mostly for tests). */
  apiBase?: string;
  /** Called with the new session_id on success. */
  onStarted?: (resp: CreateSessionResponse) => void;
  /** Called with the structured error on failure. */
  onError?: (err: { code: string; message: string }) => void;
  /** Visual / layout customisation. */
  className?: string;
  /** Accessible label (defaults to "セッションを起動"). */
  ariaLabel?: string;
}

interface UiError {
  code: string;
  message: string;
}

export function PlaySessionButton({
  prompt,
  workspace_id,
  project_id,
  bf_task_id,
  agent_persona,
  model,
  skill_name,
  user_id,
  apiBase,
  onStarted,
  onError,
  className,
  ariaLabel = "セッションを起動",
}: PlaySessionButtonProps) {
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<UiError | null>(null);

  const trimmedPrompt = prompt?.trim() ?? "";
  const disabled = loading || trimmedPrompt.length === 0;

  async function handleClick() {
    setError(null);
    setLoading(true);
    try {
      const body: CreateSessionRequest = {
        prompt: trimmedPrompt,
        workspace_id,
        project_id,
        bf_task_id,
        agent_persona,
        skill_name,
        user_id,
        run_in_background: true,
      };
      if (model) body.model = model;
      const resp = await createAgentSession(body, { apiBase });
      onStarted?.(resp);
    } catch (e) {
      const code =
        e instanceof AgentSessionError ? e.code : "agent.network_error";
      const message =
        e instanceof Error ? e.message : "unexpected error contacting the API";
      const ui = { code, message };
      setError(ui);
      onError?.(ui);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <Button
        type="button"
        onClick={handleClick}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-busy={loading || undefined}
      >
        {loading ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : (
          <Play className="size-4" aria-hidden="true" />
        )}
        <span>{loading ? "起動中…" : "起動"}</span>
      </Button>
      {error && (
        <div
          role="alert"
          className="text-xs text-destructive"
          data-error-code={error.code}
        >
          <span className="font-mono">{error.code}</span>
          {": "}
          <span>{error.message}</span>
        </div>
      )}
    </div>
  );
}
