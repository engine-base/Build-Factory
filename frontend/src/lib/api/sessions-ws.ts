/**
 * T-010d-04: SessionStreamClient — 自動 reconnect + 履歴 fetch.
 *
 * T-010d-01 backend contract:
 *   WS  /api/ws/sessions/{session_id}?since_seq=N&user_id=X
 *   GET /api/sessions/{session_id}/replay?since_seq=N
 *
 * 動作:
 *   - connect: WS open + 受信 message を on('message', ...) で配信
 *   - disconnect (unexpected): exponential backoff で reconnect, 切断時の
 *     lastSeq+1 で since_seq query を付ける (dropped frame 復元)
 *   - clean close (code 1000 / 1001 / 1008): reconnect しない
 *   - MAX_RECONNECT_ATTEMPTS 到達で 'reconnect_exhausted' を emit
 *   - close(): idempotent
 *
 * AC-1: 公開 API = SessionStreamClient class.
 * AC-2: exponential backoff (1s → 2s → 4s → ... → 30s cap) / since_seq=last+1.
 * AC-3: hook 側で REST replay fetch を先に → WS subscribe.
 * AC-4: clean close で reconnect しない / close() idempotent.
 */

import { AgentSessionError } from "@/lib/api/sessions";

export const INITIAL_RECONNECT_MS = 1000;
export const MAX_RECONNECT_MS = 30_000;
export const MAX_RECONNECT_ATTEMPTS = 8;

/** server-initiated / policy violation での "意図された" close — reconnect しない. */
export const CLEAN_CLOSE_CODES: readonly number[] = [1000, 1001, 1008] as const;

export type StreamMessage = {
  type?: string;
  seq?: number;
  /** server からの payload は opaque で保持. */
  [key: string]: unknown;
};

export type StreamEventName =
  | "message"
  | "open"
  | "close"
  | "error"
  | "reconnect_attempt"
  | "reconnect_exhausted";

export type StreamEventPayload =
  | StreamMessage          // message
  | undefined              // open / close
  | { code?: number; reason?: string }  // close detail (optional)
  | { attempt: number; delay_ms: number } // reconnect_attempt
  | { attempts: number };  // reconnect_exhausted

type Handler = (payload: StreamEventPayload) => void;

export interface SessionStreamOptions {
  apiBase?: string;
  /** override window.WebSocket (test injection). */
  WebSocketImpl?: typeof WebSocket;
  /** override setTimeout (test injection). */
  setTimeoutImpl?: typeof setTimeout;
  clearTimeoutImpl?: typeof clearTimeout;
  userId?: string;
  initialSinceSeq?: number;
}

function _httpToWs(httpBase: string): string {
  if (httpBase.startsWith("https://")) return "wss://" + httpBase.slice("https://".length);
  if (httpBase.startsWith("http://")) return "ws://" + httpBase.slice("http://".length);
  return httpBase;
}

export class SessionStreamClient {
  private readonly sessionId: number;
  private readonly opts: Required<
    Pick<SessionStreamOptions, "apiBase" | "WebSocketImpl">
  > &
    SessionStreamOptions;

  private ws: WebSocket | null = null;
  private handlers: Map<StreamEventName, Set<Handler>> = new Map();
  private lastSeq = 0;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closedByCaller = false;

  constructor(sessionId: number, opts: SessionStreamOptions = {}) {
    if (!Number.isFinite(sessionId) || sessionId <= 0) {
      throw new AgentSessionError(
        "agent.invalid_session_id",
        `sessionId must be a positive number, got ${sessionId}`,
        400,
      );
    }
    this.sessionId = sessionId;
    const base =
      opts.apiBase ??
      process.env.NEXT_PUBLIC_API_BASE ??
      "http://localhost:8001";
    const WS = opts.WebSocketImpl ?? (typeof WebSocket !== "undefined" ? WebSocket : undefined);
    if (!WS) {
      throw new AgentSessionError(
        "agent.no_websocket",
        "WebSocket not available in this runtime",
        500,
      );
    }
    this.opts = { ...opts, apiBase: base, WebSocketImpl: WS };
    if (typeof opts.initialSinceSeq === "number") {
      this.lastSeq = Math.max(0, opts.initialSinceSeq);
    }
  }

  on(event: StreamEventName, handler: Handler): () => void {
    const set = this.handlers.get(event) ?? new Set<Handler>();
    set.add(handler);
    this.handlers.set(event, set);
    return () => {
      set.delete(handler);
    };
  }

  private emit(event: StreamEventName, payload?: StreamEventPayload): void {
    const set = this.handlers.get(event);
    if (!set) return;
    for (const handler of set) {
      try {
        handler(payload);
      } catch {
        // listener が throw してもループは継続
      }
    }
  }

  start(): void {
    this.closedByCaller = false;
    this._connect();
  }

  /** idempotent close (AC-4 UNWANTED). */
  close(): void {
    this.closedByCaller = true;
    if (this.reconnectTimer !== null) {
      (this.opts.clearTimeoutImpl ?? clearTimeout)(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close(1000, "caller_closed");
      } catch {
        // ignore — already closed
      }
      this.ws = null;
    }
  }

  get currentLastSeq(): number {
    return this.lastSeq;
  }

  get currentReconnectAttempt(): number {
    return this.reconnectAttempt;
  }

  private _wsUrl(): string {
    const wsBase = _httpToWs(this.opts.apiBase);
    const sinceSeq = this.lastSeq > 0 ? this.lastSeq + 1 : 0;
    const params = new URLSearchParams();
    params.set("since_seq", String(sinceSeq));
    if (this.opts.userId) params.set("user_id", this.opts.userId);
    return `${wsBase}/api/ws/sessions/${this.sessionId}?${params.toString()}`;
  }

  private _connect(): void {
    if (this.closedByCaller) return;
    const WS = this.opts.WebSocketImpl;
    let socket: WebSocket;
    try {
      socket = new WS(this._wsUrl());
    } catch (e) {
      this.emit("error", { reason: String(e) });
      this._scheduleReconnect();
      return;
    }
    this.ws = socket;
    socket.onopen = () => {
      this.reconnectAttempt = 0;
      this.emit("open");
    };
    socket.onmessage = (ev: MessageEvent) => {
      let data: StreamMessage;
      try {
        data = JSON.parse(typeof ev.data === "string" ? ev.data : String(ev.data));
      } catch {
        return;
      }
      if (typeof data?.seq === "number" && data.seq > this.lastSeq) {
        this.lastSeq = data.seq;
      }
      this.emit("message", data);
    };
    socket.onerror = () => {
      this.emit("error");
    };
    socket.onclose = (ev: CloseEvent) => {
      this.ws = null;
      this.emit("close", { code: ev.code, reason: ev.reason });
      if (this.closedByCaller) return;
      if (CLEAN_CLOSE_CODES.includes(ev.code)) return; // AC-4 UNWANTED
      this._scheduleReconnect();
    };
  }

  private _scheduleReconnect(): void {
    if (this.closedByCaller) return;
    if (this.reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
      this.emit("reconnect_exhausted", { attempts: this.reconnectAttempt });
      return;
    }
    this.reconnectAttempt += 1;
    const delay = Math.min(
      INITIAL_RECONNECT_MS * 2 ** (this.reconnectAttempt - 1),
      MAX_RECONNECT_MS,
    );
    this.emit("reconnect_attempt", { attempt: this.reconnectAttempt, delay_ms: delay });
    const st = this.opts.setTimeoutImpl ?? setTimeout;
    this.reconnectTimer = st(() => {
      this.reconnectTimer = null;
      this._connect();
    }, delay);
  }
}

/** REST replay fetch (T-010d-01 GET endpoint). */
export async function fetchSessionReplay(
  sessionId: number,
  sinceSeq: number = 0,
  opts: { apiBase?: string; signal?: AbortSignal; userId?: string } = {},
): Promise<{ since_seq: number; count: number; items: StreamMessage[] }> {
  if (!Number.isFinite(sessionId) || sessionId <= 0) {
    throw new AgentSessionError(
      "agent.invalid_session_id",
      `sessionId must be a positive number`,
      400,
    );
  }
  const base =
    opts.apiBase ??
    process.env.NEXT_PUBLIC_API_BASE ??
    "http://localhost:8001";
  const params = new URLSearchParams();
  params.set("since_seq", String(Math.max(0, sinceSeq)));
  if (opts.userId) params.set("user_id", opts.userId);
  const resp = await fetch(
    `${base}/api/sessions/${sessionId}/replay?${params.toString()}`,
    { method: "GET", signal: opts.signal },
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
      // ignore
    }
    throw new AgentSessionError(code, message, resp.status);
  }
  return (await resp.json()) as {
    since_seq: number;
    count: number;
    items: StreamMessage[];
  };
}
