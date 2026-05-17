// @ts-nocheck
/**
 * T-V3-C-61 / S-012 — 案件ダッシュボード screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest + @testing-library/react
 *       are runtime-only devDeps for the screen test harness (wired by
 *       T-V3-C-TEST-01). Same convention as T-V3-C-37 / T-V3-C-46.
 *
 * Covers (mapped to T-V3-C-61 acceptance_criteria):
 *   structural.AC-S1  -> "h1 reads 'Build-Factory dogfood' inside data-screen-id='S-012' root"
 *   structural.AC-S2  -> "KPI labels include Phase 進捗 / Tasks / Running Sessions and sidebar groups Spec / Task / Moat / Safety / Settings / Workspace"
 *   structural.AC-S3  -> "section h2 set includes 現在のフェーズ: Phase 1 (実装) / Constitution / 最近のタスク / Pending Reviews (n) / Running Sessions (n)"
 *   structural.AC-S4  -> "no emoji glyphs — Lucide icons only"
 *   functional.AC-F1  -> "GET /api/workspaces/{id}/dashboard on mount; 4xx -> inline error + empty state"
 *   functional.AC-F2  -> "unauthenticated visitor -> /login redirect; no workspace data rendered"
 *   functional.AC-F3..F6 -> documented contracts (see page JSDoc); other Group-C UIs verify them.
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

// next/navigation is not bundled for the jsdom harness; stub useParams.
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "ws_8f3a2c" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Recharts depends on ResizeObserver which jsdom lacks; provide a no-op.
if (typeof globalThis.ResizeObserver === "undefined") {
  // @ts-expect-error — jsdom stub
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

import WorkspaceDashboardPage from "@/app/(app)/workspace/[id]/dashboard/page";

const WORKSPACE_ID = "ws_8f3a2c";
const TOKEN = "test-bearer-token";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const DASHBOARD_FIXTURE = {
  workspace: {
    id: WORKSPACE_ID,
    name: "Build-Factory dogfood",
    description: "Phase 1 開発 / 受託 SaaS の dogfood 検証",
  },
  kpi: [
    { label: "Phase 進捗", value: 64, hint: "Phase 1 / 4", progress: 64 },
    { label: "Tasks", value: "23/36", hint: "残 13 件" },
    { label: "Running Sessions", value: "5/5", hint: "swarm 稼働中" },
    { label: "Cost (this month)", value: "¥3,200", hint: "予算 ¥10,000" },
  ],
  current_phase: {
    id: "phase-1",
    name: "Phase 1: 実装",
    status: "running",
    subtitle: "基盤 + 主要画面実装 / 23 / 36 task done",
  },
  next_phase: {
    id: "phase-2",
    name: "Phase 2: 統合テスト",
    status: "locked",
    subtitle: "Locked / Phase 1 完了で自動解放",
  },
  constitution: {
    items: [
      "「Test pass = done ではない」",
      "「mock 一致は機械検証」",
      "「RLS は全 entity 必須」",
    ],
  },
  recent_tasks: [
    {
      id: "T-V3-AUTH-01",
      title: "POST /api/auth/login 実装",
      status: "done",
      assignee: "devon",
      updated_label: "2 min ago",
    },
    {
      id: "T-V3-AUTH-02",
      title: "POST /api/auth/signup 実装",
      status: "running",
      assignee: "devon",
      updated_label: "5 min ago",
    },
    {
      id: "T-V3-DB-02",
      title: "E-024 ScreenComponent 中間 table",
      status: "review",
      assignee: "winston",
      updated_label: "12 min ago",
    },
  ],
  pending_reviews: [
    {
      id: "pr-283",
      kind: "PR",
      title: "feat: auth backend complete",
      detail: "PR #283 · 12 min ago",
    },
    {
      id: "violation-12",
      kind: "赤線",
      title: "DROP query in T-024-04",
      detail: "violation #12 · 25 min ago",
    },
    {
      id: "delivery-4",
      kind: "納品",
      title: "Phase 1 partial deliverable",
      detail: "delivery #4 · 1h ago",
    },
  ],
  sessions_running_count: 5,
  sessions: [
    {
      id: "sess-1",
      task_id: "T-V3-AUTH-02",
      title: "T-V3-AUTH-02 signup impl",
      status: "running",
      persona: "DV",
      detail: "12 min · ¥41",
    },
    {
      id: "sess-2",
      task_id: "T-V3-AUTH-13",
      title: "T-V3-AUTH-13 unit test",
      status: "running",
      persona: "QN",
      detail: "3 min · ¥8",
    },
    {
      id: "sess-3",
      task_id: "T-V3-DB-03",
      title: "T-V3-DB-03 ArtifactVersion table",
      status: "running",
      persona: "WS",
      detail: "7 min · ¥22",
    },
    {
      id: "sess-4",
      task_id: "T-V3-SCR-05",
      title: "paused: T-V3-SCR-05 hearing",
      status: "paused",
      persona: "MR",
      detail: "paused 4 min ago",
    },
  ],
};

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("bf.auth.token", TOKEN);
  window.localStorage.setItem("bf.workspace.id", WORKSPACE_ID);
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      href: `http://localhost:3000/workspace/${WORKSPACE_ID}/dashboard`,
      replace: vi.fn(),
      assign: vi.fn(),
    },
  });
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(jsonResponse(200, DASHBOARD_FIXTURE));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-61 S-012 案件ダッシュボード", () => {
  it("AC-S1 + AC-S4: renders root with data-screen-id='S-012' and exact h1 'Build-Factory dogfood' with no emoji glyphs", async () => {
    render(<WorkspaceDashboardPage />);

    await waitFor(() => {
      expect(
        document.querySelector("[data-screen-id='S-012']"),
      ).not.toBeNull();
    });

    const root = document.querySelector("[data-screen-id='S-012']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe(
      "F-006,F-007,F-008,F-026",
    );
    expect(root?.getAttribute("data-screen-name")).toBe("workspace_dashboard");
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-61");
    expect(root?.getAttribute("data-entities")).toBe(
      "E-009,E-018,E-025,E-013,E-017",
    );

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent).toBe("Build-Factory dogfood");

    // AC-S4: no emoji glyphs in the rendered DOM (Lucide icons only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-S2: KPI label set includes Phase 進捗 / Tasks / Running Sessions and sidebar groups Spec / Task / Moat / Safety / Settings / Workspace", async () => {
    render(<WorkspaceDashboardPage />);

    await waitFor(() => {
      expect(
        document.querySelector("[data-screen-id='S-012']"),
      ).not.toBeNull();
    });

    const kpiLabels = Array.from(
      document.querySelectorAll("[data-kpi-label]"),
    ).map((el) => el.getAttribute("data-kpi-label"));
    expect(kpiLabels).toEqual(
      expect.arrayContaining([
        "Phase 進捗",
        "Tasks",
        "Running Sessions",
        "Cost (this month)",
      ]),
    );

    const sidebarSectionTexts = Array.from(
      document.querySelectorAll("[data-sidebar-section]"),
    ).map((el) => (el.textContent ?? "").trim());
    for (const expected of [
      "Spec",
      "Task",
      "Moat / Safety",
      "Settings",
      "Workspace",
    ]) {
      expect(sidebarSectionTexts).toContain(expected);
    }
  });

  it("AC-S3: section h2 set matches mock — 現在のフェーズ: Phase 1 (実装) / Constitution / 最近のタスク / Pending Reviews (n) / Running Sessions (n)", async () => {
    render(<WorkspaceDashboardPage />);

    await waitFor(() => {
      expect(screen.getByTestId("dashboard-recent-tasks")).toBeTruthy();
    });

    const h2Texts = Array.from(
      document.querySelectorAll("h2"),
    ).map((h) => (h.textContent ?? "").trim());

    expect(h2Texts.some((t) => t.includes("現在のフェーズ: Phase 1 (実装)"))).toBe(
      true,
    );
    expect(h2Texts.some((t) => t.includes("Constitution"))).toBe(true);
    expect(h2Texts.some((t) => t.includes("最近のタスク"))).toBe(true);
    expect(h2Texts.some((t) => /Pending Reviews \(\d+\)/.test(t))).toBe(true);
    expect(h2Texts.some((t) => /Running Sessions \(\d+\)/.test(t))).toBe(true);
  });

  it("AC-F1: on mount the page GETs /api/workspaces/{id}/dashboard and renders the 2xx body", async () => {
    render(<WorkspaceDashboardPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain(`/api/workspaces/${WORKSPACE_ID}/dashboard`);
    expect((init?.method ?? "GET")).toBe("GET");
    expect((init?.headers as Record<string, string>)?.Authorization).toBe(
      `Bearer ${TOKEN}`,
    );

    // 2xx body propagates into the page (recent tasks render).
    await waitFor(() => {
      const row = document.querySelector(
        "[data-testid='dashboard-task-row-T-V3-AUTH-01']",
      );
      expect(row).not.toBeNull();
    });
  });

  it("AC-F1 4xx branch: GET dashboard 401 surfaces an inline error toast + empty state", async () => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(
      jsonResponse(401, {
        detail: { code: "UNAUTHORIZED", message: "missing token" },
      }),
    );

    render(<WorkspaceDashboardPage />);

    const toast = await screen.findByTestId("dashboard-error-toast");
    expect(toast.getAttribute("role")).toBe("alert");
    expect(toast.textContent ?? "").toMatch(
      /サインインが必要です|通信に失敗/,
    );

    // No task rows rendered (empty state).
    expect(
      document.querySelectorAll("[data-testid^='dashboard-task-row-']").length,
    ).toBe(0);
    expect(screen.getByTestId("dashboard-tasks-empty")).toBeTruthy();
  });

  it("AC-F2: unauthenticated visitor redirects to /login and renders no workspace-scoped data", async () => {
    window.localStorage.removeItem("bf.auth.token");

    render(<WorkspaceDashboardPage />);

    await waitFor(() => {
      expect(window.location.replace).toHaveBeenCalledTimes(1);
    });
    expect(
      (window.location.replace as unknown as { mock: { calls: unknown[][] } })
        .mock.calls[0][0],
    ).toBe("/login");

    // Second half of AC-F2: no workspace data rendered.
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.queryByTestId("dashboard-recent-tasks")).toBeNull();
    expect(screen.queryByTestId("dashboard-kpi-row")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("regression: refresh button re-issues GET /api/workspaces/{id}/dashboard", async () => {
    render(<WorkspaceDashboardPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("dashboard-refresh"));

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2));
    const lastUrl = String(fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0]);
    expect(lastUrl).toContain(`/api/workspaces/${WORKSPACE_ID}/dashboard`);
  });
});
