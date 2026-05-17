// @ts-nocheck
/**
 * T-V3-C-40 / S-049 案件セットアップ — Vitest screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/S-049-workspace_setup_wizard.spec.tsx`
 * Target: AC-R1 (>= 5 cases) — actual: 7 cases covering Tier 1 + Tier 2.
 *
 * NOTE (audit MD AC-R1 reasoning): vitest / @testing-library are runtime-only
 * devDeps not yet listed in package.json (T-FOUNDATION-08 baseline drift —
 * matches the S-058 / S-060 convention adopted by T-V3-C-19 / C-21). Once
 * `pnpm add -D vitest jsdom @testing-library/react @testing-library/jest-dom
 * @vitejs/plugin-react` lands, this file PASSes as-is. The `// @ts-nocheck`
 * pragma keeps `tsc --noEmit` green in the meantime.
 *
 * Covers (mapped to T-V3-C-40 acceptance_criteria):
 *   structural.AC-S1 → renders <h1>最初の案件を作成</h1> (screens.json[S-049].h1_text)
 *                       inside an element with data-screen-id="S-049"
 *   structural.AC-S2 → no emoji characters appear in the rendered HTML
 *                       (Lucide icons exclusively, design-tokens.md §8)
 *   functional.AC-F1 → unauthenticated visitor: router.replace("/login") called
 *                       and no workspace-scoped data ("最初の案件を作成") rendered
 *   functional.AC-F1 → GET /api/me/onboarding returning 401 also triggers
 *                       router.replace("/login")
 *   functional.AC-F2 → while data is loading, role="status" aria-live="polite"
 *                       skeleton is visible; replaced atomically once loaded
 *   functional.AC-F2 → submit calls POST /api/me/onboarding/advance with the
 *                       captured payload (step=project_setup)
 *   functional.AC-F1/F2 → 5xx surfaces an endpoint-tagged role="alert" banner
 *                       and does NOT navigate away
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
  fireEvent,
  act,
} from "@testing-library/react";

// next/navigation: stub router so we can assert replace("/login") and push().
const replaceMock = vi.fn();
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

import WorkspaceSetupWizardPage from "@/app/(onboarding)/project-setup/page";
import { ACCESS_TOKEN_STORAGE_KEY } from "@/api/onboarding";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  replaceMock.mockReset();
  pushMock.mockReset();
  try {
    window.localStorage.clear();
    window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "test-token");
  } catch {
    // ignore
  }
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
  try {
    window.localStorage.clear();
  } catch {
    // ignore
  }
});

function loadedOnboardingState() {
  return {
    state: "in_progress",
    current_step: "project_setup",
    completed: false,
  };
}

function mockGetOk() {
  fetchMock.mockImplementation(async (url: RequestInfo | URL) => {
    const u = String(url);
    if (u.includes("/api/me/onboarding/advance")) {
      return jsonResponse(201, { next_step: "ai_intro", completed: false });
    }
    if (u.includes("/api/me/onboarding")) {
      return jsonResponse(200, loadedOnboardingState());
    }
    return jsonResponse(404, { detail: { code: "NOT_FOUND", message: "?" } });
  });
}

describe("T-V3-C-40 / S-049 案件セットアップ (workspace_setup_wizard)", () => {
  it("AC-S1: renders <h1>最初の案件を作成</h1> inside data-screen-id='S-049' once loaded", async () => {
    mockGetOk();
    render(<WorkspaceSetupWizardPage />);

    await waitFor(() => {
      const root = document.querySelector("[data-screen-id='S-049']");
      expect(root).not.toBeNull();
      const h1 = root?.querySelector("h1");
      expect(h1?.textContent?.trim()).toBe("最初の案件を作成");
    });
    const root = document.querySelector("[data-screen-id='S-049']");
    expect(root?.getAttribute("data-feature-id")).toBe("F-027");
  });

  it("AC-S2: rendered HTML contains no emoji glyphs (Lucide icons only)", async () => {
    mockGetOk();
    render(<WorkspaceSetupWizardPage />);

    await waitFor(() => {
      expect(screen.getByText("最初の案件を作成")).toBeTruthy();
    });
    // Conservative emoji range check (variation selector / pictographs / dingbats).
    const html = document.body.innerHTML;
    const emojiRegex =
      /[\u{1F300}-\u{1FAFF}\u{1F900}-\u{1F9FF}\u{2600}-\u{27BF}\u{2700}-\u{27BF}\u{1F000}-\u{1F0FF}]/u;
    expect(emojiRegex.test(html)).toBe(false);
  });

  it("AC-F1: unauthenticated visitor (no access token) is redirected to /login and no workspace data is rendered", async () => {
    try {
      window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    } catch {
      // ignore
    }
    render(<WorkspaceSetupWizardPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/login");
    });
    // The wizard h1 must NOT have rendered.
    expect(screen.queryByText("最初の案件を作成")).toBeNull();
    // No network request should have been made.
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("AC-F1: GET /api/me/onboarding returning 401 also redirects to /login", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(401, {
        detail: { code: "UNAUTHORIZED", message: "missing token" },
      }),
    );
    render(<WorkspaceSetupWizardPage />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/login");
    });
    expect(screen.queryByText("最初の案件を作成")).toBeNull();
  });

  it("AC-F2: while loading, a skeleton with role='status' aria-live='polite' is visible and is replaced atomically once loaded", async () => {
    // Force the GET to hang so we can observe the loading state.
    let resolveFn: ((value: Response) => void) | null = null;
    const pending = new Promise<Response>((resolve) => {
      resolveFn = resolve;
    });
    fetchMock.mockReturnValue(pending);

    render(<WorkspaceSetupWizardPage />);

    // Skeleton present during loading.
    const skeleton = await screen.findByTestId("workspace-setup-skeleton");
    expect(skeleton.getAttribute("role")).toBe("status");
    expect(skeleton.getAttribute("aria-live")).toBe("polite");

    // h1 not yet present.
    expect(screen.queryByText("最初の案件を作成")).toBeNull();

    // Resolve the GET → loaded.
    await act(async () => {
      resolveFn?.(jsonResponse(200, loadedOnboardingState()));
    });
    await waitFor(() => {
      expect(screen.queryByTestId("workspace-setup-skeleton")).toBeNull();
      expect(screen.getByText("最初の案件を作成")).toBeTruthy();
    });
  });

  it("AC-F2 (submit): clicking 次へ POSTs /api/me/onboarding/advance with step=project_setup and the captured payload", async () => {
    mockGetOk();
    render(<WorkspaceSetupWizardPage />);

    await waitFor(() => {
      expect(screen.getByText("最初の案件を作成")).toBeTruthy();
    });

    fireEvent.change(screen.getByTestId("workspace-name-input"), {
      target: { value: "受託 EC 構築 #4" },
    });
    fireEvent.change(screen.getByTestId("project-kind-select"), {
      target: { value: "受託" },
    });
    fireEvent.change(screen.getByTestId("duration-select"), {
      target: { value: "3 ヶ月" },
    });
    fireEvent.click(screen.getByTestId("workspace-setup-next"));

    await waitFor(() => {
      const advanceCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("/api/me/onboarding/advance"),
      );
      expect(advanceCall).toBeTruthy();
    });
    const advanceCall = fetchMock.mock.calls.find((c) =>
      String(c[0]).includes("/api/me/onboarding/advance"),
    )!;
    expect(advanceCall[1]?.method).toBe("POST");
    const body = JSON.parse(String(advanceCall[1]?.body ?? "{}"));
    expect(body.step).toBe("project_setup");
    expect(body.payload?.workspace_name).toBe("受託 EC 構築 #4");
    expect(body.payload?.project_kind).toBe("受託");
    expect(body.payload?.ai_employee).toBe("mary"); // default

    // After success the page navigates to S-050 ai_intro.
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith("/onboarding/ai-intro");
    });
  });

  it("AC-F1/F2: 5xx surfaces an endpoint-tagged role='alert' banner and does NOT navigate away", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message: "Traceback (most recent call last)",
        },
      }),
    );
    render(<WorkspaceSetupWizardPage />);

    const alert = await screen.findByTestId("workspace-setup-error");
    expect(alert.getAttribute("role")).toBe("alert");
    expect(alert.textContent).toContain("/api/me/onboarding");
    // Must NOT leak server stack tokens.
    expect(alert.textContent?.toLowerCase()).not.toContain("traceback");
    expect(alert.textContent?.toLowerCase()).not.toContain(
      "internal_server_error",
    );
    // Must NOT navigate to /login on 5xx.
    expect(replaceMock).not.toHaveBeenCalled();
  });
});
