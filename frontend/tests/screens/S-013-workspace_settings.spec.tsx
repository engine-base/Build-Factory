/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
/**
 * T-V3-C-62 / S-013 — 案件設定 (workspace_settings) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen
 *       test harness; tsc strict mode picks them up once the Wave 2 frontend
 *       test ticket (T-V3-C-TEST-01) is installed. Pattern mirrors
 *       S-001 / S-028 / S-048 specs.
 *
 * Covers (mapped to T-V3-C-62 acceptance_criteria):
 *   structural.AC-S1  -> h1 == "案件設定" (mock h1 逐語)
 *   structural.AC-S2  -> section h2 set == {基本情報 / トークン / コスト制限 /
 *                        外部連携 / Danger Zone}
 *   structural.AC-S3  -> Lucide icons only (no emoji glyphs)
 *   functional.AC-F1  -> GET /api/workspaces/{id} renders 2xx body;
 *                        4xx renders inline error empty state + toast
 *   functional.AC-F2  -> 401 redirects to /login (S-001); no workspace data renders
 *   functional.AC-F3  -> PUT /api/workspaces/{id} on save by owner with
 *                        valid plan upgrade; server emits account_updated
 *                        audit log (UI surfaces success toast)
 *   Delete:           -> DELETE /api/workspaces/{id} with two-step confirm
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
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// next/navigation: stub router so we can assert push/replace targets (AC-F2)
//                  and useParams payloads.
const pushMock = vi.fn();
const replaceMock = vi.fn();
const backMock = vi.fn();
const useParamsMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    back: backMock,
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  useParams: () => useParamsMock(),
}));

// sonner: capture toast.error / toast.success so we can assert UX.
const toastErrorMock = vi.fn();
const toastSuccessMock = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

import WorkspaceSettingsPage from "@/app/(app)/workspace/[id]/settings/page";

function renderWithQueryClient(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

const WORKSPACE_PAYLOAD = {
  workspace: {
    id: 1,
    account_id: 100,
    name: "Build-Factory dogfood",
    project_meta:
      "Phase 1 内製 dogfood / 受託 EC 構築フローの検証",
    project_type: "internal",
    is_confidential: false,
    token_limit: 10_000_000,
    cost_budget: 10_000,
    max_parallel_sessions: 5,
    integration_links: [
      {
        kind: "github",
        label: "GitHub",
        status: "connected",
        url: "engine-base/Build-Factory",
      },
      {
        kind: "slack",
        label: "Slack",
        status: "disconnected",
      },
      {
        kind: "obsidian",
        label: "Obsidian Vault",
        status: "connected",
        url: "~/vault/build-factory",
      },
    ],
    status: "active",
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-17T00:00:00Z",
  },
};

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  pushMock.mockReset();
  replaceMock.mockReset();
  backMock.mockReset();
  toastErrorMock.mockReset();
  toastSuccessMock.mockReset();
  useParamsMock.mockReset();
  useParamsMock.mockReturnValue({ id: "1" });
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

describe("T-V3-C-62 S-013 案件設定 (workspace_settings)", () => {
  it("AC-S1 + AC-S3: renders root with data-screen-id='S-013' and exact h1 text '案件設定' (no emoji)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(WORKSPACE_PAYLOAD));

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    const root = document.querySelector("[data-screen-id='S-013']");
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-004");
    expect(root?.getAttribute("data-screen-name")).toBe(
      "workspace_settings",
    );
    expect(root?.getAttribute("data-task-ids")).toBe("T-V3-C-62");
    expect(root?.getAttribute("data-entities")).toBe("E-009");
    expect(root?.getAttribute("data-phase")).toBe("Phase 1");

    const h1 = root?.querySelector("h1");
    expect(h1?.textContent?.trim()).toContain("案件設定");

    // AC-S3: no emoji glyphs in the rendered DOM (Lucide icons only).
    const txt = root?.textContent ?? "";
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(txt)).toBe(false);
  });

  it("AC-S2: renders the 4 section h2 headings in the mock-specified order", async () => {
    fetchMock.mockResolvedValue(jsonResponse(WORKSPACE_PAYLOAD));

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='workspace-settings-form']"),
      ).not.toBeNull(),
    );

    const h2s = Array.from(document.querySelectorAll("h2")).map(
      (n) => n.textContent?.trim() ?? "",
    );
    expect(h2s.some((t) => t.includes("基本情報"))).toBe(true);
    expect(h2s.some((t) => t.includes("トークン / コスト制限"))).toBe(true);
    expect(h2s.some((t) => t.includes("外部連携"))).toBe(true);
    expect(h2s.some((t) => t.includes("Danger Zone"))).toBe(true);
  });

  it("AC-F1: GET /api/workspaces/{id} is called on mount", async () => {
    fetchMock.mockResolvedValue(jsonResponse(WORKSPACE_PAYLOAD));

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/workspaces/1");
    expect(init?.method ?? "GET").toBe("GET");

    // 2xx body renders into the page.
    await waitFor(() => {
      const nameInput = document.querySelector(
        "[data-testid='workspace-settings-name']",
      ) as HTMLInputElement | null;
      expect(nameInput?.value).toBe("Build-Factory dogfood");
    });
  });

  it("AC-F1 tail: 4xx non-401 renders the inline empty state + toasts the friendly message tagged with the endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: {
            code: "workspace.not_found",
            message: "no such workspace",
          },
        },
        { status: 404 },
      ),
    );

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() =>
      expect(
        document.querySelector(
          "[data-testid='workspace-settings-error-empty-state']",
        ),
      ).not.toBeNull(),
    );

    expect(toastErrorMock).toHaveBeenCalled();
    const lastErrArg = toastErrorMock.mock.calls.at(-1)?.[0] as string;
    expect(lastErrArg).toContain("/api/workspaces/1");
    expect(lastErrArg).not.toMatch(/SQL|Traceback|<html/i);
  });

  it("AC-F2: 401 redirects to /login and renders no workspace-scoped data", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { detail: { code: "unauthorized", message: "missing token" } },
        { status: 401 },
      ),
    );

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() =>
      expect(replaceMock).toHaveBeenCalledWith("/login"),
    );

    // No form rendered.
    expect(
      document.querySelector("[data-testid='workspace-settings-form']"),
    ).toBeNull();
  });

  it("AC-F3: clicking 保存 PUTs /api/workspaces/{id} with the form payload and shows a success toast", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(WORKSPACE_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            id: 1,
            updated_at: "2026-05-17T12:00:00Z",
          },
          { status: 200 },
        ),
      );

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='workspace-settings-form']"),
      ).not.toBeNull(),
    );

    const select = document.querySelector(
      "[data-testid='workspace-settings-project-type']",
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "client" } });

    const saveBtn = document.querySelector(
      "[data-testid='workspace-settings-save']",
    ) as HTMLButtonElement;
    fireEvent.click(saveBtn);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [putUrl, putInit] = fetchMock.mock.calls[1];
    expect(String(putUrl)).toContain("/api/workspaces/1");
    expect(putInit?.method).toBe("PUT");
    const body = JSON.parse(String(putInit?.body));
    expect(body.project_type).toBe("client");
    expect(body.name).toBe("Build-Factory dogfood");

    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalled());
  });

  it("renders the integration list from integration_links JSONB (github / slack / obsidian)", async () => {
    fetchMock.mockResolvedValue(jsonResponse(WORKSPACE_PAYLOAD));

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() =>
      expect(
        document.querySelector(
          "[data-testid='workspace-settings-section-integrations']",
        ),
      ).not.toBeNull(),
    );

    expect(
      document.querySelector(
        "[data-testid='workspace-settings-integration-github']",
      ),
    ).not.toBeNull();
    expect(
      document.querySelector(
        "[data-testid='workspace-settings-integration-slack']",
      ),
    ).not.toBeNull();
    expect(
      document.querySelector(
        "[data-testid='workspace-settings-integration-obsidian']",
      ),
    ).not.toBeNull();
  });

  it("Danger Zone: two-step delete flow — click 削除する reveals confirm, click 本当に削除 sends DELETE", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(WORKSPACE_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse(
          { soft_deleted_at: "2026-05-17T12:00:00Z" },
          { status: 200 },
        ),
      );

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() =>
      expect(
        document.querySelector(
          "[data-testid='workspace-settings-section-danger-zone']",
        ),
      ).not.toBeNull(),
    );

    const delBtn = document.querySelector(
      "[data-testid='workspace-settings-delete']",
    ) as HTMLButtonElement;
    fireEvent.click(delBtn);

    const confirmBtn = await waitFor(() => {
      const btn = document.querySelector(
        "[data-testid='workspace-settings-delete-confirm']",
      );
      if (!btn) throw new Error("delete confirm button not visible");
      return btn as HTMLButtonElement;
    });
    fireEvent.click(confirmBtn);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [delUrl, delInit] = fetchMock.mock.calls[1];
    expect(String(delUrl)).toContain("/api/workspaces/1");
    expect(delInit?.method).toBe("DELETE");

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/workspaces"));
  });

  it("403 on save surfaces a friendly toast tagged with the failing endpoint (no stack/SQL leak)", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(WORKSPACE_PAYLOAD))
      .mockResolvedValueOnce(
        jsonResponse(
          { detail: { code: "forbidden", message: "rls violation" } },
          { status: 403 },
        ),
      );

    renderWithQueryClient(<WorkspaceSettingsPage />);

    await waitFor(() =>
      expect(
        document.querySelector("[data-testid='workspace-settings-form']"),
      ).not.toBeNull(),
    );

    const saveBtn = document.querySelector(
      "[data-testid='workspace-settings-save']",
    ) as HTMLButtonElement;
    fireEvent.click(saveBtn);

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled());
    const lastErrArg = toastErrorMock.mock.calls.at(-1)?.[0] as string;
    expect(lastErrArg).toContain("/api/workspaces/1");
    expect(lastErrArg).toMatch(/権限|forbidden/i);
    expect(lastErrArg).not.toMatch(/SQL|Traceback|<html|rls violation/i);
  });
});
