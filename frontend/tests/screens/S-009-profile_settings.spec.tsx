// @ts-nocheck
/**
 * T-V3-C-09 / S-009 — Profile settings screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket.
 *       Once installed, tsc strict mode picks them up automatically.
 *
 * Covers (mapped to T-V3-C-09 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-009"
 *   structural.AC-S2  -> "h1 text equals 'プロフィール設定'"
 *   structural.AC-S3  -> "renders 6 section h2 headings from screens.json"
 *   functional.AC-F1  -> "calls GET /api/me via typed client on mount"
 *   functional.AC-F2  -> "calls PUT /api/me on save"
 *   functional.AC-F3  -> "calls POST /api/me/api-keys on add"
 *   functional.AC-F4  -> "calls DELETE /api/me/oauth/{provider} on unlink"
 *   functional.AC-F5  -> "5xx surfaces a non-technical toast referencing the
 *                         failing endpoint without leaking stack traces"
 *   functional.AC-F6  -> "while clone_opt_in is FALSE, UI surfaces opt-out badge"
 *   functional.AC-F7  -> "opt-out path offers immediate deletion of learning data"
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
  within,
} from "@testing-library/react";

vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_API_URL: "http://localhost:8001",
    NEXT_PUBLIC_SITE_URL: "http://localhost:3001",
  },
}));

import ProfileSettingsPage from "@/app/profile/page";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;
const originalConfirm =
  typeof window !== "undefined" ? window.confirm : undefined;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const baseGetMe = {
  user: {
    id: "u-1",
    email: "masato@engine-base.com",
    name: "masato",
    avatar_url: null,
  },
  settings: {
    theme: "light",
    language: "ja",
    timezone: "Asia/Tokyo",
    notifications: {
      task_assigned: true,
      red_line: true,
      pr_review: true,
      weekly_summary: false,
    },
    clone_opt_in: false,
  },
};

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  if (typeof window !== "undefined") {
    window.confirm = vi.fn(() => true);
  }
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
  if (typeof window !== "undefined" && originalConfirm) {
    window.confirm = originalConfirm;
  }
});

async function renderLoaded() {
  fetchMock.mockResolvedValueOnce(jsonResponse(200, baseGetMe));
  const utils = render(<ProfileSettingsPage />);
  await waitFor(() =>
    expect(
      utils.container.querySelector('[data-view-state="loaded"]'),
    ).not.toBeNull(),
  );
  return utils;
}

describe("S-009 profile settings page (T-V3-C-09)", () => {
  it("AC-S1: renders root with data-screen-id='S-009'", async () => {
    const { container } = await renderLoaded();
    const root = container.querySelector('[data-screen-id="S-009"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-023");
  });

  it("AC-S2 + AC-S3: h1 matches mock and all 6 section h2 headings render", async () => {
    await renderLoaded();
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("プロフィール設定");
    const h2s = screen.getAllByRole("heading", { level: 2 }).map((n) => n.textContent ?? "");
    expect(h2s).toEqual([
      "プロフィール",
      "通知設定",
      "LLM プロバイダ (BYOK)",
      "OAuth 連携",
      "ユーザークローン (高本さんの判断基準を学習)",
      "Danger Zone",
    ]);
  });

  it("AC-F1: GET /api/me is called via typed client on mount", async () => {
    await renderLoaded();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/me");
    const init = (fetchMock.mock.calls[0][1] ?? {}) as RequestInit;
    expect(init.method).toBe("GET");
    expect((init.headers as Record<string, string>)["Accept"]).toBe(
      "application/json",
    );
  });

  it("AC-F2: clicking 保存 sends PUT /api/me with the typed client", async () => {
    const utils = await renderLoaded();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { updated_at: "2026-05-16T00:00:00Z" }),
    );
    fetchMock.mockResolvedValueOnce(jsonResponse(200, baseGetMe));

    const saveButton = utils.getByTestId("save-profile");
    fireEvent.click(saveButton);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [putUrl, putInit] = fetchMock.mock.calls[1];
    expect(String(putUrl)).toContain("/api/me");
    expect((putInit as RequestInit).method).toBe("PUT");
    const body = JSON.parse(String((putInit as RequestInit).body));
    expect(body).toHaveProperty("name");
    expect(body).toHaveProperty("settings");
  });

  it("AC-F3: submitting BYOK form sends POST /api/me/api-keys", async () => {
    const utils = await renderLoaded();
    const keyInput = utils.container.querySelector(
      "#byok-key",
    ) as HTMLInputElement;
    fireEvent.change(keyInput, { target: { value: "sk-ant-test" } });
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, { key_id: "k-1", masked_key: "sk-ant-***test" }),
    );

    fireEvent.click(utils.getByTestId("add-api-key"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(String(url)).toContain("/api/me/api-keys");
    expect((init as RequestInit).method).toBe("POST");
    const body = JSON.parse(String((init as RequestInit).body));
    expect(body.api_key).toBe("sk-ant-test");
  });

  it("AC-F4: clicking 解除 sends DELETE /api/me/oauth/{provider}", async () => {
    const utils = await renderLoaded();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { unlinked_at: "2026-05-16T00:00:00Z" }),
    );

    fireEvent.click(utils.getByTestId("unlink-github"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(String(url)).toContain("/api/me/oauth/github");
    expect((init as RequestInit).method).toBe("DELETE");
  });

  it("AC-F5: 5xx PUT surfaces a non-technical toast referencing /api/me w/o stack traces", async () => {
    const utils = await renderLoaded();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message: "Traceback (most recent call last) ... SQL FATAL",
        },
      }),
    );

    fireEvent.click(utils.getByTestId("save-profile"));

    await waitFor(() => {
      const toasts = utils.getAllByTestId("toast-error");
      expect(toasts.length).toBeGreaterThan(0);
    });
    const toast = utils.getAllByTestId("toast-error")[0];
    const text = toast.textContent ?? "";
    expect(text).toContain("/api/me");
    expect(text).not.toMatch(/traceback/i);
    expect(text).not.toMatch(/SQL/);
  });

  it("AC-F6: while clone_opt_in is FALSE, opt-out status badge is surfaced", async () => {
    const utils = await renderLoaded();
    const status = utils.queryByTestId("clone-opt-out-status");
    expect(status).not.toBeNull();
    expect(status?.textContent ?? "").toContain("user_interaction_log");
  });

  it("AC-F7: opting OUT prompts immediate deletion of learning data", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        ...baseGetMe,
        settings: { ...baseGetMe.settings, clone_opt_in: true },
      }),
    );
    const utils = render(<ProfileSettingsPage />);
    await waitFor(() =>
      expect(
        utils.container.querySelector('[data-view-state="loaded"]'),
      ).not.toBeNull(),
    );

    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { updated_at: "2026-05-16T00:00:00Z" }),
    );
    const confirmSpy = window.confirm as unknown as ReturnType<typeof vi.fn>;
    confirmSpy.mockReturnValueOnce(true);

    fireEvent.click(utils.getByTestId("clone-opt-in"));

    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    const promptText = String(confirmSpy.mock.calls[0][0] ?? "");
    expect(promptText).toContain("user_knowledge_namespace");
    expect(promptText).toContain("user_interaction_log");
  });
});
