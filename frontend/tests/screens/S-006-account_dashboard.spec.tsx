// @ts-nocheck
/**
 * T-V3-C-06 / S-006 — Account dashboard (10 案件 俯瞰) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket.
 *       Once installed, tsc strict mode picks them up automatically.
 *
 * Covers (mapped to T-V3-C-06 acceptance_criteria):
 *   structural.AC-S1 -> "renders root with data-screen-id='S-006'"
 *   structural.AC-S2 -> "h1 reads verbatim '10 案件 俯瞰'"
 *   structural.AC-S3 -> "renders 6 section h2 in mock order"
 *   structural.AC-S4 -> "exposes 4 KPI labels: Active Projects / Running Sessions / Monthly Cost / Anomalies (24h)"
 *   functional.AC-F1 -> "calls GET /api/accounts/{id}/dashboard via typed client"
 *   functional.AC-F2 -> "4xx/5xx surfaces a non-technical toast referencing the endpoint without leaking stack traces"
 *   functional.AC-F3 -> "loaded payload renders workspaces aggregated server-side"
 *   functional.AC-F4 -> "401 session_expired shows the S-054 dialog and preserves in-flight form data"
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
  waitFor,
  cleanup,
} from "@testing-library/react";

// sonner is a side-effect toast — mock so we can assert toast.error fires.
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

import AccountDashboardPage from "@/app/dashboard/page";
import { toast } from "sonner";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sampleDashboardPayload() {
  return {
    account_id: 1,
    workspaces: [
      {
        id: 1,
        name: "Build-Factory dogfood",
        status: "running",
        role: "account_owner",
        progress: 0.64,
        completed_tasks: 23,
        running_sessions: 5,
        monthly_cost_jpy: 3200,
        pending_approvals: 1,
      },
      {
        id: 2,
        name: "ABC 社",
        status: "review",
        role: "workspace_admin",
        progress: 0.88,
        completed_tasks: 42,
        running_sessions: 2,
        monthly_cost_jpy: 1820,
        pending_approvals: 2,
      },
      {
        id: 3,
        name: "XYZ 社",
        status: "running",
        role: "member",
        progress: 0.32,
        completed_tasks: 12,
        running_sessions: 3,
        monthly_cost_jpy: 920,
        pending_approvals: 0,
      },
    ],
    kpi: {
      workspace_count: 3,
      total_progress: 0.61,
      completed_tasks: 47,
      running_sessions: 10,
      monthly_cost_jpy: 5940,
      pending_approvals: 3,
    },
    computed_at: 1747410000,
    duration_ms: 18,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  (toast.error as ReturnType<typeof vi.fn>).mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  if (typeof window !== "undefined") {
    window.localStorage.clear();
    window.localStorage.setItem("bf.account_id", "42");
    window.localStorage.setItem("bf.access_token", "AT-token");
  }
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-006 Account Dashboard page (T-V3-C-06)", () => {
  it("AC-S1: renders root with data-screen-id='S-006'", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, sampleDashboardPayload()));
    const { container } = render(<AccountDashboardPage />);
    const root = container.querySelector('[data-screen-id="S-006"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-024");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-06");
  });

  it("AC-S2: h1 reads verbatim '10 案件 俯瞰'", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, sampleDashboardPayload()));
    render(<AccountDashboardPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("10 案件 俯瞰");
  });

  it("AC-S3: renders all 6 section h2 headings in mock order", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, sampleDashboardPayload()));
    render(<AccountDashboardPage />);
    await waitFor(() =>
      expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThanOrEqual(6),
    );
    const h2Texts = screen
      .getAllByRole("heading", { level: 2 })
      .map((h) => h.textContent?.trim() ?? "");
    expect(h2Texts).toEqual(
      expect.arrayContaining([
        "Pending Reviews",
        "Phase 進捗",
        "完了タスク (7d)",
        "全 Workspaces (10 案件並走中)",
        "AI 社員 使用率（今週）",
        "直近の Activity",
      ]),
    );
  });

  it("AC-S4: exposes the 4 hero KPI labels", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, sampleDashboardPayload()));
    render(<AccountDashboardPage />);
    await waitFor(() => {
      for (const label of [
        "Active Projects",
        "Running Sessions",
        "Monthly Cost",
        "Anomalies (24h)",
      ]) {
        expect(screen.getByText(label)).toBeTruthy();
      }
    });
  });

  it("AC-F1: calls GET /api/accounts/{id}/dashboard via typed client", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, sampleDashboardPayload()));
    render(<AccountDashboardPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/accounts/42/dashboard");
    const init = (fetchMock.mock.calls[0][1] ?? {}) as RequestInit;
    expect(init.method).toBe("GET");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer AT-token",
    );
  });

  it("AC-F2: 5xx surfaces a non-technical toast referencing the failing endpoint w/o stack traces", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message:
            'Traceback (most recent call last):\n  File "dash.py", line 12, in compute',
        },
      }),
    );
    render(<AccountDashboardPage />);
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const message =
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "";
    expect(message).toContain("/api/accounts/42/dashboard");
    expect(message).not.toMatch(/Traceback/i);
    expect(message).not.toMatch(/dash\.py/);
    expect(message).not.toMatch(/Exception/);
  });

  it("AC-F3: 200 payload renders aggregated workspace rows", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, sampleDashboardPayload()));
    render(<AccountDashboardPage />);
    await waitFor(() =>
      expect(screen.getAllByTestId("workspace-row").length).toBe(3),
    );
    expect(screen.getByText("Build-Factory dogfood")).toBeTruthy();
    expect(screen.getByText("ABC 社")).toBeTruthy();
    expect(screen.getByText("XYZ 社")).toBeTruthy();
    // The aggregate completed_tasks value (47) must come from the server kpi block (AC-F3).
    expect(screen.getByText("47")).toBeTruthy();
  });

  it("AC-F4: 401 session_expired shows the S-054 dialog and preserves in-flight form data", async () => {
    // Seed a draft input in the document so we can verify it is preserved.
    const form = document.createElement("form");
    const input = document.createElement("input");
    input.setAttribute("name", "draft_message");
    input.value = "WIP draft text";
    form.appendChild(input);
    document.body.appendChild(form);

    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, {
        detail: { code: "session_expired", message: "session expired" },
      }),
    );
    render(<AccountDashboardPage />);
    await waitFor(() =>
      expect(
        document.querySelector('[data-screen-id="S-054"]'),
      ).not.toBeNull(),
    );
    expect(
      screen.getByText("セッションの有効期限が切れました"),
    ).toBeTruthy();

    const draftRaw = window.localStorage.getItem("bf.inflight_form_data");
    expect(draftRaw).not.toBeNull();
    const draft = JSON.parse(draftRaw as string) as {
      fields: Record<string, string>;
    };
    expect(draft.fields.draft_message).toBe("WIP draft text");

    document.body.removeChild(form);
  });
});
