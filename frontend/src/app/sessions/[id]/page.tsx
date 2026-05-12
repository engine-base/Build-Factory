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
  type SwarmLogLine,
  type SwarmSessionData,
} from "@/lib/api/sessions";

export default function SwarmSessionPage() {
  const params = useParams();
  const rawId = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const sessionId = rawId ? Number(rawId) : Number.NaN;

  const [session, setSession] = React.useState<SwarmSessionData | null>(null);
  const [logs] = React.useState<SwarmLogLine[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState<boolean>(true);

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
      <h1 className="mb-4 text-lg font-semibold text-slate-800">
        Swarm Session #{session.id}
      </h1>
      <SwarmSessionDetail
        session={session}
        logs={logs}
        onResume={handleResume}
      />
    </main>
  );
}
