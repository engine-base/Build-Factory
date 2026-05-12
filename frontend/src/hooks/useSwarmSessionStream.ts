/**
 * T-010d-04: useSwarmSessionStream — REST replay (履歴 fetch) → WS subscribe
 *             (自動 reconnect) を React hook で統合する.
 *
 * 動作:
 *   1. mount 時に GET /api/sessions/{id}/replay?since_seq=0 で履歴取得
 *   2. SessionStreamClient.start() で WS subscribe (since_seq=lastSeq+1)
 *   3. unmount 時に AbortController + close で cleanup
 *
 * 戻り値: { logs, connected, lastSeq, reconnectAttempt, error }
 *
 * AC-3 STATE-DRIVEN: replay → WS の順序 / no flash-of-empty.
 * AC-4 UNWANTED: invalid sessionId で WS 開かない / 404 で empty graceful.
 */

import * as React from "react";

import { AgentSessionError } from "@/lib/api/sessions";
import type { SwarmLogLine } from "@/lib/api/sessions";
import {
  SessionStreamClient,
  fetchSessionReplay,
  type StreamMessage,
} from "@/lib/api/sessions-ws";

export interface UseSwarmSessionStreamOptions {
  /** WS / REST base URL を override (test injection). */
  apiBase?: string;
  /** WS impl を override (test injection). */
  WebSocketImpl?: typeof WebSocket;
  /** actor user_id を audit query に乗せる. */
  userId?: string;
  /** false なら subscribe しない (一時停止用). */
  enabled?: boolean;
}

export interface UseSwarmSessionStreamResult {
  logs: SwarmLogLine[];
  connected: boolean;
  lastSeq: number;
  reconnectAttempt: number;
  error: string | null;
  /** caller が任意に close / restart したいときに使う. */
  client: SessionStreamClient | null;
}

function _messageToLogLine(msg: StreamMessage): SwarmLogLine {
  const time =
    typeof msg.time === "number" || typeof msg.time === "string"
      ? (msg.time as number | string)
      : Date.now() / 1000;
  const tool = typeof msg.tool === "string" ? msg.tool : undefined;
  const status = typeof msg.status === "string" ? msg.status : String(msg.text ?? "");
  const kind =
    msg.kind === "tool" || msg.kind === "status" || msg.kind === "error" || msg.kind === "stdout"
      ? msg.kind
      : "stdout";
  return { time, tool, status, kind };
}

export function useSwarmSessionStream(
  sessionId: number,
  opts: UseSwarmSessionStreamOptions = {},
): UseSwarmSessionStreamResult {
  const [logs, setLogs] = React.useState<SwarmLogLine[]>([]);
  const [connected, setConnected] = React.useState(false);
  const [lastSeq, setLastSeq] = React.useState(0);
  const [reconnectAttempt, setReconnectAttempt] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);
  const [client, setClient] = React.useState<SessionStreamClient | null>(null);

  const enabled = opts.enabled !== false;
  const apiBase = opts.apiBase;
  const userId = opts.userId;
  const WebSocketImpl = opts.WebSocketImpl;

  React.useEffect(() => {
    // AC-4 UNWANTED: invalid sessionId は WS 開かない
    if (!enabled) return;
    if (!Number.isFinite(sessionId) || sessionId <= 0) {
      setError("invalid sessionId");
      setConnected(false);
      return;
    }

    const controller = new AbortController();
    let active = true;
    setError(null);

    // 1. 履歴 fetch (AC-3 STATE-DRIVEN: replay → WS の順序)
    fetchSessionReplay(sessionId, 0, {
      apiBase,
      signal: controller.signal,
      userId,
    })
      .then((data) => {
        if (!active) return;
        const initial = data.items.map(_messageToLogLine);
        setLogs(initial);
        if (data.items.length > 0) {
          const maxSeq = data.items.reduce(
            (acc, m) => (typeof m.seq === "number" && m.seq > acc ? m.seq : acc),
            0,
          );
          if (maxSeq > 0) setLastSeq(maxSeq);
        }
      })
      .catch((e: unknown) => {
        if (!active) return;
        if (e instanceof AgentSessionError) {
          // 404 → graceful empty state (AC-4 UNWANTED)
          if (e.status === 404) {
            setLogs([]);
            setError(null);
          } else {
            setError(`${e.code}: ${e.message}`);
          }
        } else if (e instanceof Error && e.name !== "AbortError") {
          setError(e.message);
        }
      });

    // 2. WS subscribe
    let streamClient: SessionStreamClient | null = null;
    try {
      streamClient = new SessionStreamClient(sessionId, {
        apiBase,
        userId,
        WebSocketImpl,
      });
    } catch (e: unknown) {
      if (e instanceof AgentSessionError) {
        setError(`${e.code}: ${e.message}`);
      }
      return () => {
        active = false;
        controller.abort();
      };
    }

    streamClient.on("open", () => {
      if (!active) return;
      setConnected(true);
    });
    streamClient.on("close", () => {
      if (!active) return;
      setConnected(false);
    });
    streamClient.on("message", (payload) => {
      if (!active) return;
      const msg = payload as StreamMessage;
      const line = _messageToLogLine(msg);
      setLogs((prev) => [...prev, line]);
      if (typeof msg?.seq === "number") {
        setLastSeq((prev) => (msg.seq! > prev ? msg.seq! : prev));
      }
    });
    streamClient.on("reconnect_attempt", (payload) => {
      if (!active) return;
      const p = payload as { attempt: number; delay_ms: number };
      setReconnectAttempt(p.attempt);
    });
    streamClient.on("reconnect_exhausted", () => {
      if (!active) return;
      setError("reconnect attempts exhausted");
      setConnected(false);
    });
    streamClient.on("error", () => {
      if (!active) return;
      setConnected(false);
    });

    streamClient.start();
    setClient(streamClient);

    return () => {
      active = false;
      controller.abort();
      streamClient?.close();
    };
  }, [sessionId, enabled, apiBase, userId, WebSocketImpl]);

  return { logs, connected, lastSeq, reconnectAttempt, error, client };
}
