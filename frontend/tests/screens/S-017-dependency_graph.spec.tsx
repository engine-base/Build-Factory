// @ts-nocheck
/**
 * T-V3-C-38 / S-017 — 依存グラフ (DAG) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket
 *       (T-V3-C-TEST-01). Same convention as T-V3-C-12 / C-25.
 *
 * Covers (mapped to T-V3-C-38 acceptance_criteria):
 *   structural.AC-S1  -> "h1 reads '依存グラフ (DAG)'"
 *   structural.AC-S2  -> "renders root with data-screen-id=S-017"
 *   functional.AC-F1  -> "GET /api/workspaces/{id}/dependencies via typed client on mount"
 *   functional.AC-F1  -> "4xx surfaces non-technical toast + empty state"
 *   functional.AC-F2  -> "401 -> redirect /login + no workspace data rendered"
 *   functional.AC-F3  -> "POST /api/workspaces/{id}/dependencies on 依存追加 submit"
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
} from "@testing-library/react";

import DependencyGraphPage from "@/app/(app)/spec/dependencies/page";

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

const DEPENDENCIES_FIXTURE = {
  dependencies: [
    {
      id: "dep-1",
      from_task_id: "T-V3-INFRA-01",
      to_task_id: "T-V3-AUTH-01",
      kind: "hard",
    },
    {
      id: "dep-2",
      from_task_id: "T-V3-AUTH-01",
      to_task_id: "T-V3-AUTH-13",
      kind: "hard",
    },
  ],
  tasks: [
    { id: "T-V3-INFRA-01", title: "ADR-013 AUTH 戦略", status: "done", phase: "Phase 1" },
    { id: "T-V3-AUTH-01", title: "POST /api/auth/login", status: "running", phase: "Phase 1" },
    { id: "T-V3-AUTH-13", title: "unit test 8 cases", status: "todo", phase: "Phase 1" },
  ],
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
    url.endsWith("/dependencies")
  ) {
    return Promise.resolve(jsonResponse(200, DEPENDENCIES_FIXTURE));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
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

describe("S-017 依存グラフ (DAG) page (T-V3-C-38)", () => {
  it("AC-S2: renders root with data-screen-id='S-017'", async () => {
    const { container } = render(<DependencyGraphPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-017"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-009");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-38");
    expect(root?.getAttribute("data-entities")).toContain("E-019");
  });

  it("AC-S1: h1 reads '依存グラフ (DAG)'", async () => {
    render(<DependencyGraphPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("依存グラフ (DAG)");
  });

  it("AC-F1: GET /api/workspaces/{id}/dependencies on mount via typed client", async () => {
    render(<DependencyGraphPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toContain("/api/workspaces/ws-test/dependencies");
    expect((init ?? {}).method ?? "GET").toBe("GET");
    // Backend body should be rendered into the page (AC-F1 — render 2xx body).
    await waitFor(() =>
      expect(screen.queryByTestId("dependency-row-dep-1")).not.toBeNull(),
    );
    expect(screen.getByTestId("dependency-row-dep-2")).not.toBeNull();
  });

  it("AC-F1: 4xx surfaces a non-technical toast referencing the endpoint and renders an empty state", async () => {
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

    render(<DependencyGraphPage />);

    await waitFor(() =>
      expect(screen.queryByTestId("dependency-graph-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("dependency-graph-error");
    expect(banner.textContent).toContain("/api/workspaces/ws-test/dependencies");
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(banner.textContent?.toLowerCase()).not.toContain("/srv/app.py");
    // Empty state visible.
    expect(screen.queryByTestId("dag-empty")).not.toBeNull();
    // No workspace dep rows rendered.
    expect(screen.queryByTestId("dependency-row-dep-1")).toBeNull();
  });

  it("AC-F2: 401 from GET dependencies redirects to /login and does not render workspace-scoped data", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, {
          detail: { code: "UNAUTHORIZED", message: "missing token" },
        }),
      ),
    );

    render(<DependencyGraphPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    // No workspace dependency rows or error toast rendered (AC-F2 UNWANTED).
    expect(screen.queryByTestId("dependency-row-dep-1")).toBeNull();
    expect(screen.queryByTestId("dependency-graph-error")).toBeNull();
  });

  it("AC-F3: POST /api/workspaces/{id}/dependencies when 依存追加 form is submitted", async () => {
    render(<DependencyGraphPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("add-dep-open"));

    fireEvent.change(screen.getByLabelText(/from_task_id/), {
      target: { value: "T-V3-INFRA-01" },
    });
    fireEvent.change(screen.getByLabelText(/to_task_id/), {
      target: { value: "T-V3-AUTH-02" },
    });

    fetchMock.mockImplementationOnce((url: string, init?: RequestInit) => {
      if (
        typeof url === "string" &&
        url.endsWith("/api/workspaces/ws-test/dependencies") &&
        init?.method === "POST"
      ) {
        return Promise.resolve(
          jsonResponse(200, { dependency_id: "dep-3" }),
        );
      }
      return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
    });
    fetchMock.mockImplementationOnce(defaultFetchImpl);

    fireEvent.submit(screen.getByTestId("add-dep-form"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const postCall = fetchMock.mock.calls[1];
    expect(String(postCall[0])).toContain(
      "/api/workspaces/ws-test/dependencies",
    );
    expect(postCall[1].method).toBe("POST");
    const payload = JSON.parse(String(postCall[1].body));
    expect(payload.from_task_id).toBe("T-V3-INFRA-01");
    expect(payload.to_task_id).toBe("T-V3-AUTH-02");
    expect(payload.kind).toBe("hard");
  });

  it("AC-F3: 409 (cycle detected) from POST surfaces an endpoint-referenced message", async () => {
    render(<DependencyGraphPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("add-dep-open"));
    fireEvent.change(screen.getByLabelText(/from_task_id/), {
      target: { value: "T-A" },
    });
    fireEvent.change(screen.getByLabelText(/to_task_id/), {
      target: { value: "T-A" },
    });

    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        jsonResponse(409, {
          detail: { code: "CONFLICT", message: "cycle detected" },
        }),
      ),
    );

    fireEvent.submit(screen.getByTestId("add-dep-form"));

    await waitFor(() =>
      expect(screen.queryByTestId("dependency-graph-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("dependency-graph-error");
    expect(banner.textContent).toContain(
      "/api/workspaces/ws-test/dependencies",
    );
    expect(banner.textContent).toContain("循環");
  });
});
