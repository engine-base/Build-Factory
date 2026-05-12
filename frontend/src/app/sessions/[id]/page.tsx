"use client";

/**
 * T-010d-03: /sessions/[id] — swarm session 詳細ページ.
 *
 * App Router dynamic segment. useParams で session_id を取り出し、
 * fetchAgentSession() で詳細取得 → SwarmSessionDetail で描画.
 *
 * resume button click → resumeAgentSession() (T-S0-08 4-choice resume).
 *
 * AC-4 UNWANTED: 404 で empty-state / logs 空で placeholder /
 * component が fetch 直接呼ばない (page 責務).
 */

import * as React from "react";
import { useParams } from "next/navigation";

import { SwarmSessionDetail } from "@/components/sessions/SwarmSessionDetail";
import {
  AgentSessionError,
  fetchAgentSession,
  resumeAgentSession,
  type ResumeChoice,
  type SwarmSessionData,
} from "@/lib/api/sessions";
import { useSwarmSessionStream } from "@/hooks/useSwarmSessionStream";

export default function SwarmSessionPage() {
  const params = useParams();
  const rawId = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const sessionId = rawId ? Number(rawId) : Number.NaN;

  const [session, setSession] = React.useState<SwarmSessionData | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);

  // T-010d-04: 履歴 fetch + WS 自動 reconnect
  const stream = useSwarmSessionStream(sessionId, {
    enabled: Number.isFinite(sessionId) && sessionId > 0,
  });
  const logs = stream.logs;

  React.useEffect(() => {
    if (!Number.isFinite(sessionId)) {
      setError("invalid session id");
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    fetchAgentSession(sessionId, { signal: controller.signal })
      .then((s) => {
        setSession(s);
        setError(null);
      })
      .catch((e: unknown) => {
        if (e instanceof AgentSessionError) {
          if (e.status === 404) {
            setError("session not found");
          } else {
            setError(`${e.code}: ${e.message}`);
          }
        } else if (e instanceof Error) {
          setError(e.message);
        } else {
          setError("unknown error");
        }
        setSession(null);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [sessionId]);

  const handleResume = React.useCallback(
    async (choice: ResumeChoice) => {
      if (!session) return;
      try {
        await resumeAgentSession(session.id, choice);
        // 再取得 (audit_logs に worktree.created など発生する可能性)
        const updated = await fetchAgentSession(session.id);
        setSession(updated);
      } catch (e: unknown) {
        if (e instanceof AgentSessionError) {
          setError(`${e.code}: ${e.message}`);
        } else if (e instanceof Error) {
          setError(e.message);
        }
      }
    },
    [session],
  );

  if (loading) {
    return (
      <main className="mx-auto max-w-4xl p-6">
        <p className="text-sm text-slate-500">Loading…</p>
      </main>
    );
  }

  if (error || !session) {
    return (
      <main className="mx-auto max-w-4xl p-6">
        <h1 className="text-lg font-semibold text-slate-800">
          Swarm Session
        </h1>
        <p
          className="mt-2 text-sm text-rose-600"
          data-testid="session-error-state"
        >
          {error ?? "session not found"}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">
          Swarm Session #{session.id}
        </h1>
        <div
          className="flex items-center gap-2 text-xs text-slate-500"
          data-testid="connection-status"
        >
          {stream.connected ? (
            <>
              <span className="h-2 w-2 rounded-full bg-eb-500" />
              <span>connected · seq {stream.lastSeq}</span>
            </>
          ) : stream.reconnectAttempt > 0 ? (
            <>
              <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
              <span>reconnecting (attempt {stream.reconnectAttempt})</span>
            </>
          ) : (
            <>
              <span className="h-2 w-2 rounded-full bg-slate-400" />
              <span>{stream.error ?? "disconnected"}</span>
            </>
          )}
        </div>
      </div>
      <SwarmSessionDetail
        session={session}
        logs={logs}
        onResume={handleResume}
      />
    </main>
  );
}
