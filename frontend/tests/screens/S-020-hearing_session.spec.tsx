// @ts-nocheck
/**
 * T-V3-C-46 / S-020 — ヒアリングセッション screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are runtime-only devDeps for the screen test harness (wired by
 *       T-V3-C-TEST-01). Same convention as T-V3-C-37 / T-V3-C-39.
 *
 * Covers (mapped to T-V3-C-46 acceptance_criteria):
 *   structural.AC-S1  -> "h1 reads 'ヒアリングセッション' inside data-screen-id='S-020' root"
 *   structural.AC-S2  -> "no emoji glyphs — Lucide icons only"
 *   functional.AC-F1  -> "WS /ws/hearing/{session_id} on mount; close ≥ 4000 → inline error + empty state"
 *   functional.AC-F2  -> "unauthenticated visitor → /login redirect; no workspace data rendered"
 *   functional.AC-F3  -> "WS streams chat messages and slot_state updates"
 *   regression        -> "POST /api/workspaces/{id}/hearing/save when Save is clicked"
 */

import * as React from "react";
import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";

vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_API_URL: "http://localhost:8001",
    NEXT_PUBLIC_SITE_URL: "http://localhost:3001",
  },
}));

import HearingSessionPage from "@/app/(app)/spec/hearing/page";

// --------------------------------------------------------------------------
// Fixtures
// --------------------------------------------------------------------------

const WORKSPACE_ID = "ws_8f3a2c";
const SESSION_ID = "session_abc123";
const TOKEN = "test-bearer-token";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// --------------------------------------------------------------------------
// Mock WebSocket — captures instances so tests can drive open/message/close.
// --------------------------------------------------------------------------

class MockWebSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: MockWebSocket[] = [];

  url: string;
  readyState = 0; // CONNECTING
  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  CONNECTING = 0;
  OPEN = 1;
  CLOSING = 2;
  CLOSED = 3;

  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(code?: number, reason?: string): void {
    this.readyState = 3;
    this.onclose?.({
      code: code ?? 1000,
      reason: reason ?? "",
      wasClean: true,
    } as CloseEvent);
  }

  /** Test helper — push a server frame. */
  emitMessage(frame: unknown): void {
    this.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent);
  }

  /** Test helper — flip to OPEN. */
  emitOpen(): void {
    this.readyState = 1;
    this.onopen?.({} as Event);
  }

  /** Test helper — close with a 4xx-equivalent code. */
  emitClose(code: number, reason = ""): void {
    this.readyState = 3;
    this.onclose?.({ code, reason, wasClean: false } as CloseEvent);
  }
}

const originalWebSocket = globalThis.WebSocket;
const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

beforeEach(() => {
  MockWebSocket.instances = [];
  // jsdom exposes `localStorage` and `location`.
  window.localStorage.clear();
  // Default: authenticated user with workspace + session ids set.
  window.localStorage.setItem("bf.auth.token", TOKEN);
  window.localStorage.setItem("bf.workspace.id", WORKSPACE_ID);
  window.localStorage.setItem("bf.hearing.session_id", SESSION_ID);
  // Mute location.replace so AC-F2 can assert it was called.
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      href: "http://localhost:3000/spec/hearing",
      replace: vi.fn(),
      assign: vi.fn(),
    },
  });
  // Inject WebSocket mock.
  (globalThis as { WebSocket?: typeof WebSocket }).WebSocket =
    MockWebSocket as unknown as typeof WebSocket;
  // Inject fetch mock.
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  (globalThis as { WebSocket?: typeof WebSocket }).WebSocket =
    originalWebSocket;
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-46 S-020 ヒアリングセッション", () => {
  it("AC-S1 + AC-S2: renders root with data-screen-id='S-020' and exact h1 'ヒアリングセッション'", async () => {
    render(<HearingSessionPage />);

    await waitFor(() => {
      expect(
        document.querySelector("[data-screen-id='S-020']"),
      ).not.toBeNull();
    });

    const root = document.querySelector("[data-screen-id='S-020']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-005");
    expect(root?.getAttribute("data-screen-name")).toBe("hearing_session");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.includes("ヒアリングセッション")).toBe(true);

    // AC-S2: no emoji glyphs in the rendered DOM (Lucide icons only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-F2: unauthenticated visitor redirects to /login and renders no workspace-scoped data", async () => {
    window.localStorage.removeItem("bf.auth.token");

    render(<HearingSessionPage />);

    await waitFor(() => {
      expect(window.location.replace).toHaveBeenCalledTimes(1);
    });
    expect(
      (window.location.replace as unknown as { mock: { calls: unknown[][] } })
        .mock.calls[0][0],
    ).toBe("/login");

    // AC-F2 second half: no workspace data is rendered.
    expect(screen.queryByTestId("hearing-chat-log")).toBeNull();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("AC-F1: on mount the WS connection targets /ws/hearing/{session_id}", async () => {
    render(<HearingSessionPage />);

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1);
    });
    const ws = MockWebSocket.instances[0];
    expect(ws.url).toContain(`/ws/hearing/${SESSION_ID}`);
    // Token piggybacks the URL because browsers cannot set WS headers.
    expect(ws.url).toContain(`token=${encodeURIComponent(TOKEN)}`);
  });

  it("AC-F3: WS message + slot_state frames stream into the chat log and sidebar", async () => {
    render(<HearingSessionPage />);

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1);
    });
    const ws = MockWebSocket.instances[0];
    ws.emitOpen();

    ws.emitMessage({
      type: "message",
      message: {
        id: "m1",
        role: "ai",
        author: "mary (BA)",
        created_at: "2026-05-17T14:32:00Z",
        content: "こんにちは、mary です。",
      },
    });
    ws.emitMessage({
      type: "slot_state",
      slot: {
        key: "vision",
        label: "ビジョン",
        status: "filled",
        extracted: "開発工場 OS / SaaS",
      },
    });

    await waitFor(() => {
      const log = screen.getByTestId("hearing-chat-log");
      expect(log.textContent).toContain("こんにちは、mary です。");
    });
    const slot = await screen.findByTestId("hearing-slot-vision");
    expect(slot.getAttribute("data-testid")).toBe("hearing-slot-vision");
    expect(slot.textContent).toContain("開発工場 OS / SaaS");
  });

  it("AC-F1 4xx branch: WS close code ≥ 4000 surfaces an inline error toast and empty state", async () => {
    render(<HearingSessionPage />);

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1);
    });
    const ws = MockWebSocket.instances[0];
    ws.emitOpen();
    ws.emitClose(4401, "unauthorized");

    const toast = await screen.findByTestId("hearing-error-toast");
    expect(toast.getAttribute("role")).toBe("alert");
    expect(toast.textContent ?? "").toMatch(
      /サインインが必要です|ヒアリング|処理に失敗|通信に失敗/,
    );
    // No chat messages were rendered because the stream errored before any frame.
    expect(document.querySelectorAll("[data-testid='hearing-message']").length).toBe(
      0,
    );
  });

  it("regression: clicking 成果物保存 POSTs to /api/workspaces/{id}/hearing/save", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(201, {
        hearing_id: "hr_xyz",
        saved_at: "2026-05-17T14:40:00Z",
      }),
    );

    render(<HearingSessionPage />);

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1);
    });
    MockWebSocket.instances[0].emitOpen();

    fireEvent.click(screen.getByTestId("hearing-save-button"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(
      `/api/workspaces/${WORKSPACE_ID}/hearing/save`,
    );
    expect(init?.method).toBe("POST");
    const body = JSON.parse(String(init?.body ?? "{}"));
    expect(body.session_id).toBe(SESSION_ID);
  });
});
