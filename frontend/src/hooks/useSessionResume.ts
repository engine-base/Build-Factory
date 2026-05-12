/**
 * T-010c-06: useSessionResume — 4 choice resume の round-trip.
 *
 * UI button click → POST /api/agent/sessions/{id}/resume (T-S0-08 +
 * T-010d-03 sessions.ts resumeAgentSession) → 成功時 fetchAgentSession で
 * 再取得 → state 更新.
 *
 * deterministic status mapping (claude_agent_runner.handle_resume と整合):
 *   cancel          → 'cancelled'
 *   manual_fix      → 'paused'
 *   from_checkpoint → 'running' (run_task 経由)
 *   rerun_full      → 'running' (run_task 経由 / 新 SDK session)
 *
 * AC-1: useSessionResume(sessionId, opts) → {resume, isResuming, lastChoice,
 *        lastStatus, error}. sessions.ts の VALID_RESUME_CHOICES を再 import
 *        (再定義禁止 / T-S0-08 / T-010d-03 cross-module invariant).
 * AC-2: round-trip = POST + audit emit + re-fetch.
 * AC-3: isResuming true は POST + re-fetch window のみ.
 * AC-4: invalid sessionId / invalid choice / 404 / 並行呼出 serialize.
 */

import * as React from "react";

import {
  AgentSessionError,
  fetchAgentSession,
  resumeAgentSession,
  VALID_RESUME_CHOICES,
  type ResumeChoice,
  type SwarmSessionData,
} from "@/lib/api/sessions";

export interface UseSessionResumeOptions {
  apiBase?: string;
  userId?: string;
  /** resume 成功時 (session 更新後) に呼ばれる callback. */
  onSession?: (session: SwarmSessionData) => void;
}

export interface UseSessionResumeResult {
  resume: (choice: ResumeChoice) => Promise<void>;
  isResuming: boolean;
  lastChoice: ResumeChoice | null;
  lastStatus: string | null;
  error: string | null;
}

/** deterministic mapping (handle_resume と整合 / AC-3 STATE-DRIVEN). */
export const RESUME_CHOICE_TO_EXPECTED_STATUS: Record<ResumeChoice, string> = {
  cancel: "cancelled",
  manual_fix: "paused",
  from_checkpoint: "running",
  rerun_full: "running",
};

export function useSessionResume(
  sessionId: number,
  opts: UseSessionResumeOptions = {},
): UseSessionResumeResult {
  const [isResuming, setIsResuming] = React.useState(false);
  const [lastChoice, setLastChoice] = React.useState<ResumeChoice | null>(null);
  const [lastStatus, setLastStatus] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // AC-4 UNWANTED: 並行呼出 serialize (refs で第二呼出を弾く)
  const inflightRef = React.useRef<boolean>(false);
  const onSessionRef = React.useRef(opts.onSession);
  onSessionRef.current = opts.onSession;

  const resume = React.useCallback(
    async (choice: ResumeChoice) => {
      // AC-4: invalid sessionId は backend 呼ばない
      if (!Number.isFinite(sessionId) || sessionId <= 0) {
        setError("invalid sessionId");
        return;
      }
      // AC-4: invalid choice (VALID_RESUME_CHOICES に無い) は backend 前で reject
      if (!VALID_RESUME_CHOICES.includes(choice)) {
        setError(`invalid choice: ${choice}`);
        return;
      }
      // AC-4: 並行呼出 dedupe
      if (inflightRef.current) {
        return;
      }
      inflightRef.current = true;
      setIsResuming(true);
      setError(null);

      try {
        // round-trip step 1: POST /resume (T-S0-08 backend + T-010d-03 helper)
        const resp = await resumeAgentSession(sessionId, choice, {
          apiBase: opts.apiBase,
        });
        setLastChoice(choice);
        setLastStatus(resp.status);

        // round-trip step 2: 最新 session を再取得して state を一致させる
        try {
          const updated = await fetchAgentSession(sessionId, {
            apiBase: opts.apiBase,
          });
          setLastStatus(String(updated.status ?? resp.status));
          onSessionRef.current?.(updated);
        } catch {
          // re-fetch 失敗は warn 扱い (resume 自体は成功)
        }
      } catch (e: unknown) {
        if (e instanceof AgentSessionError) {
          setError(`${e.code}: ${e.message}`);
        } else if (e instanceof Error) {
          setError(e.message);
        } else {
          setError("unknown error");
        }
      } finally {
        setIsResuming(false);
        inflightRef.current = false;
      }
    },
    [sessionId, opts.apiBase],
  );

  return { resume, isResuming, lastChoice, lastStatus, error };
}
