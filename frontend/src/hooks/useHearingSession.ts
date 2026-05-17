/**
 * T-V3-C-46 / S-020 / F-005 — Hearing session hook.
 *
 * Manages the WebSocket subscription to WS /ws/hearing/{session_id} plus
 * the POST save mutation against /api/workspaces/{id}/hearing/save.
 *
 * AC mapping:
 *   AC-F1 (EVENT-DRIVEN WS mount + 4xx → inline error) — exposes `error` /
 *          `isError` / `readyState` on the hook return so the page can render
 *          an inline error toast + empty state on close codes ≥ 4000.
 *   AC-F3 (EVENT-DRIVEN WS streams chat + slot_state)  — `messages` /
 *          `slotStates` accumulate from incoming `message` / `slot_state`
 *          frames.
 *   AC-F2 (UNWANTED unauthenticated → /login)          — surfaced by the
 *          page via `authToken === null` short-circuit; the hook itself
 *          treats a missing token as "do not connect".
 *
 * The hook deliberately does not depend on TanStack Query for the WS stream
 * (cf. the spec/phases page) so jsdom-based tests can drive a stub
 * WebSocket implementation deterministically.
 */

"use client";

import * as React from "react";

import {
  HearingSessionApiError,
  buildHearingWsUrl,
  parseHearingStreamEvent,
  saveHearing,
  type HearingChatMessage,
  type HearingSaveRequest,
  type HearingSaveResponse,
  type HearingSlotState,
  type HearingStreamEvent,
} from "@/api/hearing-session";

/** Public ready-state for the WS subscription (mirror of WebSocket numeric states). */
export type HearingReadyState =
  | "idle"
  | "connecting"
  | "open"
  | "closing"
  | "closed";

export interface UseHearingSessionParams {
  /** Hearing session id — required to open the WS connection. */
  sessionId: string | null;
  /** Workspace id — required for the save mutation. */
  workspaceId: string | null;
  /** Bearer token; when null the hook stays idle (no WS, no fetch). */
  authToken: string | null;
  /** Optional WebSocket implementation override (jsdom tests). */
  webSocketImpl?: typeof WebSocket;
  /** Optional fetch implementation override (jsdom tests). */
  fetchImpl?: typeof fetch;
  /** Optional API base override (jsdom tests inject `http://localhost`). */
  apiBase?: string;
  /** Test seam — auto-connect WS on mount (default true). */
  autoConnect?: boolean;
}

export interface UseHearingSessionResult {
  messages: HearingChatMessage[];
  slotStates: HearingSlotState[];
  /** True while the WS is connecting or open. */
  isStreaming: boolean;
  readyState: HearingReadyState;
  /** Latest error (HearingSessionApiError | Event-like close info | null). */
  error: HearingSessionApiError | Error | null;
  /** True iff the latest WS close or save call surfaced an error. */
  isError: boolean;
  /** Trigger POST /api/workspaces/{id}/hearing/save with the given title. */
  save: (title?: string | null) => Promise<HearingSaveResponse>;
  isSaving: boolean;
  saved: HearingSaveResponse | null;
  /** Manual close — flushes the WebSocket. */
  disconnect: () => void;
  /** Manual reconnect — closes any active socket and re-opens. */
  reconnect: () => void;
}

function mapReadyState(state: number | null | undefined): HearingReadyState {
  switch (state) {
    case 0:
      return "connecting";
    case 1:
      return "open";
    case 2:
      return "closing";
    case 3:
      return "closed";
    default:
      return "idle";
  }
}

/**
 * useHearingSession — WS stream subscription + save mutation for S-020.
 *
 * Test seam: callers can inject `webSocketImpl` / `fetchImpl` / `apiBase` so
 * vitest specs run deterministically against a stub WebSocket without
 * touching the real network.
 */
export function useHearingSession(
  params: UseHearingSessionParams,
): UseHearingSessionResult {
  const {
    sessionId,
    workspaceId,
    authToken,
    webSocketImpl,
    fetchImpl,
    apiBase,
    autoConnect = true,
  } = params;

  const [messages, setMessages] = React.useState<HearingChatMessage[]>([]);
  const [slotStates, setSlotStates] = React.useState<HearingSlotState[]>([]);
  const [readyState, setReadyState] = React.useState<HearingReadyState>("idle");
  const [error, setError] = React.useState<
    HearingSessionApiError | Error | null
  >(null);
  const [isSaving, setIsSaving] = React.useState(false);
  const [saved, setSaved] = React.useState<HearingSaveResponse | null>(null);

  const wsRef = React.useRef<WebSocket | null>(null);
  const reconnectKeyRef = React.useRef(0);

  const applyEvent = React.useCallback((evt: HearingStreamEvent) => {
    switch (evt.type) {
      case "message":
        setMessages((prev) => [...prev, evt.message]);
        break;
      case "slot_state":
        setSlotStates((prev) => {
          const next = prev.filter((s) => s.key !== evt.slot.key);
          next.push(evt.slot);
          return next;
        });
        break;
      case "error":
        setError(
          new HearingSessionApiError(
            evt.code,
            evt.message,
            0,
            `/ws/hearing/${sessionId ?? ""}`,
          ),
        );
        break;
      // `typing` / `end` are not surfaced as state on the hook return; the
      // page reads readyState + isStreaming for transient indicators.
      default:
        break;
    }
  }, [sessionId]);

  // Connect / reconnect the WebSocket whenever the inputs change.
  React.useEffect(() => {
    if (!autoConnect) return;
    if (!sessionId || !authToken) {
      setReadyState("idle");
      return;
    }
    if (typeof window === "undefined") return;
    const Impl = webSocketImpl ?? (globalThis as { WebSocket?: typeof WebSocket }).WebSocket;
    if (!Impl) {
      setReadyState("idle");
      return;
    }

    const url = buildHearingWsUrl(sessionId, { apiBase, authToken });

    let socket: WebSocket;
    try {
      socket = new Impl(url);
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setReadyState("closed");
      return;
    }
    wsRef.current = socket;
    setReadyState(mapReadyState(socket.readyState));
    setError(null);

    socket.onopen = () => {
      setReadyState("open");
    };
    socket.onmessage = (evt: MessageEvent) => {
      const raw = typeof evt.data === "string" ? evt.data : "";
      const parsed = parseHearingStreamEvent(raw);
      if (parsed) applyEvent(parsed);
    };
    socket.onerror = () => {
      setError(
        new HearingSessionApiError(
          "WS_ERROR",
          "websocket error",
          0,
          `/ws/hearing/${sessionId}`,
        ),
      );
    };
    socket.onclose = (evt: CloseEvent) => {
      setReadyState("closed");
      // close code ≥ 4000 → AC-F1 4xx-equivalent (inline error + empty state).
      if (evt.code >= 4000 && evt.code < 5000) {
        setError(
          new HearingSessionApiError(
            `WS_${evt.code}`,
            evt.reason || "session closed",
            evt.code,
            `/ws/hearing/${sessionId}`,
          ),
        );
      }
    };

    return () => {
      try {
        if (
          socket.readyState === socket.OPEN ||
          socket.readyState === socket.CONNECTING
        ) {
          socket.close();
        }
      } catch {
        /* noop */
      }
      wsRef.current = null;
    };
    // reconnectKey is read for force-re-runs from reconnect().
  }, [
    sessionId,
    authToken,
    autoConnect,
    apiBase,
    webSocketImpl,
    applyEvent,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    reconnectKeyRef.current,
  ]);

  const disconnect = React.useCallback(() => {
    const sock = wsRef.current;
    if (sock) {
      try {
        sock.close();
      } catch {
        /* noop */
      }
      wsRef.current = null;
      setReadyState("closed");
    }
  }, []);

  const reconnect = React.useCallback(() => {
    disconnect();
    reconnectKeyRef.current += 1;
    setMessages([]);
    setSlotStates([]);
    setError(null);
    setReadyState("connecting");
  }, [disconnect]);

  const save = React.useCallback(
    async (title?: string | null): Promise<HearingSaveResponse> => {
      if (!workspaceId || !sessionId) {
        const endpoint = workspaceId
          ? `/api/workspaces/${workspaceId}/hearing/save`
          : "/api/workspaces/<unknown>/hearing/save";
        const err = new HearingSessionApiError(
          "MISSING_CONTEXT",
          "workspace_id or session_id is missing",
          0,
          endpoint,
        );
        setError(err);
        throw err;
      }
      setIsSaving(true);
      setError(null);
      try {
        const body: HearingSaveRequest = {
          session_id: sessionId,
          ...(title ? { title } : {}),
        };
        const resp = await saveHearing(workspaceId, body, {
          authToken,
          apiBase,
          fetchImpl,
        });
        setSaved(resp);
        return resp;
      } catch (err) {
        const wrapped =
          err instanceof HearingSessionApiError
            ? err
            : new HearingSessionApiError(
                "UNKNOWN",
                err instanceof Error ? err.message : String(err),
                0,
                `/api/workspaces/${workspaceId}/hearing/save`,
              );
        setError(wrapped);
        throw wrapped;
      } finally {
        setIsSaving(false);
      }
    },
    [workspaceId, sessionId, authToken, apiBase, fetchImpl],
  );

  return {
    messages,
    slotStates,
    isStreaming: readyState === "connecting" || readyState === "open",
    readyState,
    error,
    isError: error !== null,
    save,
    isSaving,
    saved,
    disconnect,
    reconnect,
  };
}
