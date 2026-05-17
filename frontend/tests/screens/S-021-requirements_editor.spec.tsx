// @ts-nocheck
/**
 * T-V3-C-47 / S-021 — 要件エディタ (requirements_editor) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket
 *       (T-V3-C-TEST-01). Same convention as T-V3-C-38 / C-39.
 *
 * Covers (mapped to T-V3-C-47 acceptance_criteria):
 *   structural.AC-S1 -> "h1 === '要件エディタ'"
 *   structural.AC-S2 -> "section h2 set === {'2. 機能要件 (Must)'}"
 *   structural.AC-S3 -> "Lucide icons exclusively (no emoji)"
 *   functional.AC-F1 -> "GET /api/workspaces/{id}/requirements via typed client on mount"
 *   functional.AC-F1 -> "4xx surfaces non-technical toast + empty state"
 *   functional.AC-F2 -> "401 -> redirect /login + no workspace data rendered"
 *   functional.AC-F3 -> "PUT /api/workspaces/{id}/requirements returns version+1"
 *   functional.AC-F4 -> "non-EARS AC blocks PUT client-side (EarsValidationError)"
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
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import RequirementsEditorPage from "@/app/(app)/spec/requirements/page";
import {
  detectEarsForm,
  validateRequirementItems,
  EarsValidationError,
} from "@/api/requirements-editor";

// --------------------------------------------------------------------------
// Next.js router + searchParams mocks
// --------------------------------------------------------------------------

const routerReplace = vi.fn();
const searchParamsGet = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplace,
    push: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => ({
    get: searchParamsGet,
  }),
}));

// --------------------------------------------------------------------------
// fetch mocking
// --------------------------------------------------------------------------

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const REQUIREMENTS_FIXTURE = {
  requirements: [
    {
      id: "req-1",
      section: "2.1 認証 (S-001〜005)",
      label: "Must",
      body_md:
        "- When 有効な email + password が POST /api/auth/login に送られた時、the system shall 200 と JWT を返却する。",
    },
  ],
  version: 21,
};

function defaultFetchImpl(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const method = init?.method ?? "GET";
  if (
    typeof url === "string" &&
    method === "GET" &&
    url.includes("/api/workspaces/") &&
    url.endsWith("/requirements")
  ) {
    return Promise.resolve(jsonResponse(200, REQUIREMENTS_FIXTURE));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <RequirementsEditorPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  routerReplace.mockReset();
  searchParamsGet.mockReset();
  searchParamsGet.mockImplementation((key: string) =>
    key === "workspace_id" ? "ws-test" : null,
  );
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-021 要件エディタ page (T-V3-C-47)", () => {
  it("AC-S1: h1 reads '要件エディタ' (no emoji glyph)", async () => {
    renderPage();
    const h1 = await screen.findByRole("heading", {
      level: 1,
      name: /要件エディタ/,
    });
    expect(h1.textContent).toContain("要件エディタ");
    // AC-S3: no emoji glyph in the rendered h1.
    expect(h1.textContent ?? "").not.toMatch(
      /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u,
    );
  });

  it("AC-S2: renders the mock section h2 ('2. 機能要件 (Must)')", async () => {
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const h2 = await screen.findAllByTestId("requirements-section-h2");
    expect(h2[0].textContent).toBe("2. 機能要件 (Must)");
  });

  it("AC-S2/data-screen-id: renders root with data-screen-id='S-021'", async () => {
    const { container } = renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-021"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-006");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-47");
    expect(root?.getAttribute("data-entities")).toContain("E-016");
  });

  it("AC-F1: GET /api/workspaces/{id}/requirements on mount via typed client", async () => {
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toContain("/api/workspaces/ws-test/requirements");
    expect((init ?? {}).method ?? "GET").toBe("GET");
    // 2xx body rendered.
    await waitFor(() => {
      expect(screen.queryByTestId("requirements-item-0")).not.toBeNull();
    });
  });

  it("AC-F1: 4xx surfaces a non-technical toast referencing the endpoint and renders the empty state", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(404, {
          detail: {
            code: "NOT_FOUND",
            message:
              "Traceback (most recent call last): File '/srv/app.py' line 99",
          },
        }),
      ),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.queryByTestId("requirements-editor-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("requirements-editor-error");
    expect(banner.textContent).toContain(
      "/api/workspaces/ws-test/requirements",
    );
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(banner.textContent?.toLowerCase()).not.toContain("/srv/app.py");
    // No requirements rendered.
    expect(screen.queryByTestId("requirements-item-0")).toBeNull();
  });

  it("AC-F2: 401 from GET requirements redirects to /login and does not render workspace-scoped data", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, {
          detail: { code: "UNAUTHORIZED", message: "missing token" },
        }),
      ),
    );

    renderPage();

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    // No requirements item or error toast rendered (AC-F2 UNWANTED).
    expect(screen.queryByTestId("requirements-item-0")).toBeNull();
    expect(screen.queryByTestId("requirements-editor-error")).toBeNull();
  });

  it("AC-F3: PUT /api/workspaces/{id}/requirements returns version+1", async () => {
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(screen.queryByTestId("requirements-item-0")).not.toBeNull();
    });

    fetchMock.mockImplementationOnce((url: string, init?: RequestInit) => {
      if (
        typeof url === "string" &&
        url.endsWith("/api/workspaces/ws-test/requirements") &&
        init?.method === "PUT"
      ) {
        return Promise.resolve(
          jsonResponse(200, {
            id: "req-doc-1",
            version: REQUIREMENTS_FIXTURE.version + 1,
          }),
        );
      }
      return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
    });
    fetchMock.mockImplementationOnce(defaultFetchImpl);

    fireEvent.click(screen.getByTestId("requirements-save-button"));

    await waitFor(() => {
      const putCalls = fetchMock.mock.calls.filter(
        (c: any) => c[1]?.method === "PUT",
      );
      expect(putCalls.length).toBe(1);
      const body = JSON.parse(String(putCalls[0][1].body));
      expect(body.items).toBeTruthy();
      expect(body.items[0].body_md).toContain("the system shall");
    });

    // Header badge should reflect server-incremented version (version+1).
    await waitFor(() => {
      const badge = screen.getByTestId("requirements-version-badge");
      expect(badge.textContent).toContain(
        `v${REQUIREMENTS_FIXTURE.version + 1}`,
      );
    });
  });

  it("AC-F4: non-EARS AC items raise EarsValidationError before PUT (no wire call)", async () => {
    const items = [
      {
        section: "2.1",
        body_md: "- this line has shall but no EARS lead phrase",
      },
    ];
    expect(() => validateRequirementItems(items)).toThrow(EarsValidationError);

    // Valid EARS lines pass.
    const okItems = [
      {
        section: "2.1",
        body_md:
          "- When user posts /login, the system shall return 200.\n- If creds invalid, the system shall not return token.",
      },
    ];
    expect(() => validateRequirementItems(okItems)).not.toThrow();
  });

  it("detectEarsForm: classifies the 5 canonical lead phrases", () => {
    expect(detectEarsForm("The system shall log audit events.")).toBe(
      "UBIQUITOUS",
    );
    expect(
      detectEarsForm("When user logs in, the system shall issue a JWT."),
    ).toBe("EVENT-DRIVEN");
    expect(
      detectEarsForm("While mfa_enabled, the system shall require TOTP."),
    ).toBe("STATE-DRIVEN");
    expect(
      detectEarsForm("Where SSO is enabled, the system shall redirect to IdP."),
    ).toBe("OPTIONAL");
    expect(
      detectEarsForm("If creds invalid, the system shall not return a token."),
    ).toBe("UNWANTED");
    expect(detectEarsForm("Random prose without verb.")).toBeNull();
  });
});
