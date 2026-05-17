// @ts-nocheck
/**
 * T-V3-C-37 / S-016 — フェーズ管理 screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are runtime-only devDeps for the screen test harness (wired by
 *       T-V3-C-TEST-01). Same convention as T-V3-C-04 / C-07 / C-11 / C-12.
 *
 * Covers (mapped to T-V3-C-37 acceptance_criteria):
 *   structural.AC-S1  -> "h1 reads 'フェーズ管理' inside the data-screen-id='S-016' root"
 *   structural.AC-S2  -> "renders h2 'Phase Timeline'"
 *   structural.AC-S3  -> "no emoji glyphs — Lucide icons only"
 *   functional.AC-F1  -> "GET /api/workspaces/{id}/phases on mount; 4xx -> inline error + empty state"
 *   functional.AC-F2  -> "unauthenticated visitor -> /login redirect; no workspace data rendered"
 *   functional.AC-F3  -> "POST /api/workspaces/{id}/phases/{phase_id}/gate -> next phase unlocked"
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

import PhasesPage from "@/app/(app)/spec/phases/page";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const PHASES_FIXTURE = {
  phases: [
    {
      id: "phase-impl",
      name: "実装",
      status: "running",
      start_date: "2026-03-05T00:00:00Z",
      end_date: "2026-06-30T00:00:00Z",
      progress: 64,
      gate_conditions: [
        { id: "c1", label: "全 main task が done", satisfied: true },
        { id: "c2", label: "赤線抵触 = 0", satisfied: true },
        { id: "c3", label: "integration test PASS", satisfied: false },
        { id: "c4", label: "クライアント承認 (S-035)", satisfied: false },
      ],
    },
    {
      id: "phase-test",
      name: "統合テスト",
      status: "locked",
      start_date: "2026-07-01T00:00:00Z",
      end_date: "2026-07-31T00:00:00Z",
      progress: 0,
      gate_conditions: [
        { id: "d1", label: "E2E PASS", satisfied: false },
      ],
    },
  ],
  current_phase_id: "phase-impl",
};

const WORKSPACE_ID = "ws_8f3a2c";
const TOKEN = "test-bearer-token";

const PHASES_URL = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/phases`;
const GATE_URL_IMPL = `http://localhost:8001/api/workspaces/${WORKSPACE_ID}/phases/phase-impl/gate`;

function defaultFetchImpl(url: string, init?: RequestInit): Promise<Response> {
  const method = init?.method ?? "GET";
  if (typeof url === "string" && method === "GET" && url === PHASES_URL) {
    return Promise.resolve(jsonResponse(200, PHASES_FIXTURE));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

function primeAuth(workspaceId: string | null = WORKSPACE_ID) {
  window.localStorage.setItem("bf.auth.token", TOKEN);
  if (workspaceId) {
    window.localStorage.setItem("bf.workspace.id", workspaceId);
  }
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
  try {
    window.localStorage.clear();
  } catch {
    /* jsdom localStorage may be unavailable in some envs */
  }
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-016 フェーズ管理 page (T-V3-C-37)", () => {
  it("AC-S1: renders root with data-screen-id='S-016' and h1 'フェーズ管理'", async () => {
    primeAuth();
    const { container } = render(<PhasesPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-016"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-008");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-37");
    expect(root?.getAttribute("data-entities")).toContain("E-013");
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("フェーズ管理");
  });

  it("AC-S2: renders section h2 'Phase Timeline'", async () => {
    primeAuth();
    render(<PhasesPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const h2s = screen.getAllByRole("heading", { level: 2 });
    expect(h2s.some((h) => (h.textContent ?? "").includes("Phase Timeline"))).toBe(true);
  });

  it("AC-S3: uses Lucide icons exclusively (no emoji glyphs)", async () => {
    primeAuth();
    const { container } = render(<PhasesPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const text = container.textContent ?? "";
    // 絵文字禁止 (design-tokens.md §8). Match emoji ranges defensively.
    const emojiPattern =
      /[\u{1F300}-\u{1FAFF}\u{1F600}-\u{1F64F}\u{1F900}-\u{1F9FF}\u{2600}-\u{27BF}]/u;
    expect(emojiPattern.test(text)).toBe(false);
  });

  it("AC-F1: GET /api/workspaces/{id}/phases on mount via typed client and renders the 2xx body", async () => {
    primeAuth();
    render(<PhasesPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toBe(PHASES_URL);
    expect((init ?? {}).method ?? "GET").toBe("GET");
    expect(String((init ?? {}).headers?.Authorization ?? "")).toContain(TOKEN);
    await waitFor(() =>
      expect(screen.queryByTestId("phase-row-phase-impl")).not.toBeNull(),
    );
    expect(screen.getByTestId("phase-row-phase-test")).not.toBeNull();
  });

  it("AC-F1 (UNWANTED): 4xx renders an inline error banner and an empty state, with no workspace rows", async () => {
    primeAuth();
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(403, {
          detail: {
            code: "FORBIDDEN",
            message:
              "Traceback (most recent call last): File '/srv/app.py' line 1",
          },
        }),
      ),
    );
    render(<PhasesPage />);
    await waitFor(() =>
      expect(screen.queryByTestId("phases-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("phases-error");
    expect(banner.textContent).toContain(`/api/workspaces/${WORKSPACE_ID}/phases`);
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(screen.queryByTestId("phases-empty")).not.toBeNull();
    expect(screen.queryByTestId("phase-row-phase-impl")).toBeNull();
  });

  it("AC-F2 (UNWANTED): unauthenticated visitor redirects to /login and renders no workspace-scoped data", async () => {
    // No primeAuth() — localStorage clear means no token.
    const replaceMock = vi.fn();
    const originalReplace = window.location.replace;
    Object.defineProperty(window.location, "replace", {
      configurable: true,
      value: replaceMock,
    });
    try {
      const { container } = render(<PhasesPage />);
      await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
      // No fetch happened — the page must not surface workspace rows or KPIs.
      expect(fetchMock).not.toHaveBeenCalled();
      expect(container.textContent ?? "").not.toContain("Phase Timeline");
    } finally {
      Object.defineProperty(window.location, "replace", {
        configurable: true,
        value: originalReplace,
      });
    }
  });

  it("AC-F3: POST /api/workspaces/{id}/phases/{phase_id}/gate unlocks the next phase on 201", async () => {
    primeAuth();
    render(<PhasesPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    // Override fixture so all gate conditions are satisfied -> button enabled.
    fetchMock.mockReset();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (method === "GET" && url === PHASES_URL) {
        return Promise.resolve(
          jsonResponse(200, {
            phases: [
              {
                id: "phase-impl",
                name: "実装",
                status: "running",
                progress: 100,
                gate_conditions: [
                  { id: "c1", label: "all done", satisfied: true },
                ],
              },
              {
                id: "phase-test",
                name: "統合テスト",
                status: "locked",
                progress: 0,
                gate_conditions: [],
              },
            ],
            current_phase_id: "phase-impl",
          }),
        );
      }
      if (method === "POST" && url === GATE_URL_IMPL) {
        return Promise.resolve(
          jsonResponse(201, {
            unlocked_phase_id: "phase-test",
            evaluated_at: "2026-05-17T00:00:00Z",
          }),
        );
      }
      return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
    });

    fireEvent.click(screen.getByTestId("phases-refresh"));
    await waitFor(() =>
      expect(screen.queryByTestId("phase-gate-trigger-phase-impl")).not.toBeNull(),
    );

    const btn = screen.getByTestId("phase-gate-trigger-phase-impl");
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(btn);

    // 1 refresh GET, 1 gate POST, 1 follow-up GET refresh after success.
    await waitFor(() => {
      const postCalls = fetchMock.mock.calls.filter(
        ([url, init]) =>
          typeof url === "string" &&
          url === GATE_URL_IMPL &&
          init?.method === "POST",
      );
      expect(postCalls.length).toBe(1);
    });
    await waitFor(() =>
      expect(screen.queryByTestId("phases-toast-success")).not.toBeNull(),
    );
    expect(screen.getByTestId("phases-toast-success").textContent).toContain(
      "phase-test",
    );
  });
});
