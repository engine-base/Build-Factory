// @ts-nocheck
/**
 * T-V3-C-59 / S-029 — タスク DAG (task_dag_view) screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the screen
 *       test harness; they are wired by the Wave 2 frontend test setup
 *       ticket (T-V3-C-TEST-01). Same convention as T-V3-C-51 / C-38 / C-39.
 *
 * Covers (mapped to T-V3-C-59 acceptance_criteria):
 *   structural.AC-S1  -> 'h1 reads "タスク DAG"'
 *   structural.AC-S2  -> 'renders root with data-screen-id=S-029'
 *   functional.AC-F1  -> 'GET /api/workspaces/{id}/tasks/dag via typed client on mount'
 *   functional.AC-F1  -> '4xx surfaces non-technical toast + empty state'
 *   functional.AC-F2  -> '401 -> redirect /login + no workspace data rendered'
 *   functional.AC-F3  -> 'GET /api/workspaces/{id}/tasks?group_by=feature returns
 *                         accordion-friendly metadata'
 *   functional.AC-F4  -> 'POST /api/workspaces/{id}/dependencies on submit'
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

import TaskDagViewPage from "@/app/(app)/task/dag/page";

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

const TASK_DAG_FIXTURE = {
  nodes: [
    {
      id: "T-V3-AUTH-01",
      title: "login API",
      status: "running",
      wave: 1,
      feature_id: "F-001",
    },
    {
      id: "T-V3-AUTH-02",
      title: "signup API",
      status: "todo",
      wave: 1,
      feature_id: "F-001",
    },
    {
      id: "T-V3-AUTH-04",
      title: "MFA enroll",
      status: "blocked",
      wave: 1,
      feature_id: "F-001",
    },
    {
      id: "T-V3-AUTH-08",
      title: "/login page",
      status: "todo",
      wave: 2,
      feature_id: "F-001",
    },
  ],
  edges: [
    {
      from_task_id: "T-V3-AUTH-01",
      to_task_id: "T-V3-AUTH-08",
      type: "blocks",
    },
    {
      from_task_id: "T-V3-AUTH-02",
      to_task_id: "T-V3-AUTH-04",
      type: "soft",
    },
  ],
};

const BY_FEATURE_FIXTURE = {
  groups: [
    {
      feature_id: "F-001",
      feature_title: "AUTH",
      tasks: [
        { id: "T-V3-AUTH-01", title: "login API", status: "running" },
        { id: "T-V3-AUTH-02", title: "signup API", status: "todo" },
      ],
      done_count: 0,
      total_count: 4,
    },
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
    url.endsWith("/tasks/dag")
  ) {
    return Promise.resolve(jsonResponse(200, TASK_DAG_FIXTURE));
  }
  if (
    typeof url === "string" &&
    method === "GET" &&
    url.includes("/api/workspaces/") &&
    url.includes("/tasks?group_by=feature")
  ) {
    return Promise.resolve(jsonResponse(200, BY_FEATURE_FIXTURE));
  }
  if (
    typeof url === "string" &&
    method === "POST" &&
    url.includes("/api/workspaces/") &&
    url.endsWith("/dependencies/impact-analysis")
  ) {
    return Promise.resolve(
      jsonResponse(200, {
        affected_tasks: [
          { id: "T-V3-AUTH-08", title: "/login page", status: "todo" },
        ],
        blast_radius: 1,
      }),
    );
  }
  if (
    typeof url === "string" &&
    method === "POST" &&
    url.includes("/api/workspaces/") &&
    url.endsWith("/dependencies")
  ) {
    return Promise.resolve(
      jsonResponse(200, { dependency_id: "dep-new-1" }),
    );
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

describe("S-029 タスク DAG page (T-V3-C-59)", () => {
  it("AC-S2: renders root with data-screen-id='S-029'", async () => {
    const { container } = render(<TaskDagViewPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-029"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-007");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-59");
    expect(root?.getAttribute("data-entities")).toContain("E-018");
  });

  it("AC-S1: h1 reads 'タスク DAG'", async () => {
    render(<TaskDagViewPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("タスク DAG");
  });

  it("AC-F1: GET /api/workspaces/{id}/tasks/dag on mount via typed client", async () => {
    render(<TaskDagViewPage />);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) =>
          String(u).includes("/api/workspaces/ws-test/tasks/dag"),
        ),
      ).toBe(true),
    );
    // Backend body should be rendered into the page (AC-F1 — render 2xx body).
    await waitFor(() =>
      expect(
        screen.queryByTestId("dag-node-T-V3-AUTH-01"),
      ).not.toBeNull(),
    );
    expect(screen.getByTestId("dag-node-T-V3-AUTH-02")).not.toBeNull();
    expect(screen.getByTestId("dag-node-T-V3-AUTH-04")).not.toBeNull();
    expect(
      screen.getByTestId("dag-edge-T-V3-AUTH-01-T-V3-AUTH-08"),
    ).not.toBeNull();
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

    render(<TaskDagViewPage />);

    await waitFor(() =>
      expect(screen.queryByTestId("task-dag-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("task-dag-error");
    expect(banner.textContent).toContain(
      "/api/workspaces/ws-test/tasks/dag",
    );
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(banner.textContent?.toLowerCase()).not.toContain("/srv/app.py");
    expect(screen.queryByTestId("dag-empty")).not.toBeNull();
    expect(screen.queryByTestId("dag-node-T-V3-AUTH-01")).toBeNull();
  });

  it("AC-F2: 401 from GET tasks/dag redirects to /login and does not render workspace-scoped data", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(401, {
          detail: { code: "UNAUTHORIZED", message: "missing token" },
        }),
      ),
    );

    render(<TaskDagViewPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByTestId("dag-node-T-V3-AUTH-01")).toBeNull();
    expect(screen.queryByTestId("task-dag-error")).toBeNull();
  });

  it("AC-F3: GET /tasks?group_by=feature populates the accordion with done/total metadata", async () => {
    render(<TaskDagViewPage />);
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([u]) =>
          String(u).includes(
            "/api/workspaces/ws-test/tasks?group_by=feature",
          ),
        ),
      ).toBe(true),
    );

    await waitFor(() =>
      expect(screen.queryByTestId("feature-group-F-001")).not.toBeNull(),
    );
    // Accordion is collapsed by default; toggle to expand.
    const toggle = screen.getByTestId("feature-toggle-F-001");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("feature-tasks-F-001")).not.toBeNull();
    // The accordion-friendly done/total badge should be visible inside the
    // group toggle button ("0 / 4" per fixture).
    expect(toggle.textContent).toContain("0 / 4");
  });

  it("AC-F4: POST /api/workspaces/{id}/dependencies on add-dependency submit", async () => {
    render(<TaskDagViewPage />);
    await waitFor(() =>
      expect(
        screen.queryByTestId("dag-node-T-V3-AUTH-01"),
      ).not.toBeNull(),
    );

    const fromInput = screen.getByTestId("dep-from") as HTMLInputElement;
    const toInput = screen.getByTestId("dep-to") as HTMLInputElement;
    fireEvent.change(fromInput, { target: { value: "T-V3-AUTH-01" } });
    fireEvent.change(toInput, { target: { value: "T-V3-AUTH-08" } });

    const submit = screen.getByTestId("dep-submit");
    fireEvent.click(submit);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, init]) =>
            String(u).endsWith(
              "/api/workspaces/ws-test/dependencies",
            ) && (init?.method ?? "GET") === "POST",
        ),
      ).toBe(true),
    );

    const call = fetchMock.mock.calls.find(
      ([u, init]) =>
        String(u).endsWith("/api/workspaces/ws-test/dependencies") &&
        (init?.method ?? "GET") === "POST",
    );
    expect(call).toBeTruthy();
    const body = JSON.parse(String(call?.[1]?.body ?? "{}"));
    expect(body.from_task_id).toBe("T-V3-AUTH-01");
    expect(body.to_task_id).toBe("T-V3-AUTH-08");
  });

  it("AC-F4: clicking a node triggers POST /dependencies/impact-analysis and renders the side panel", async () => {
    render(<TaskDagViewPage />);
    await waitFor(() =>
      expect(
        screen.queryByTestId("dag-node-T-V3-AUTH-01"),
      ).not.toBeNull(),
    );

    fireEvent.click(screen.getByTestId("dag-node-T-V3-AUTH-01"));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, init]) =>
            String(u).endsWith(
              "/api/workspaces/ws-test/dependencies/impact-analysis",
            ) && (init?.method ?? "GET") === "POST",
        ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("impact-result")).not.toBeNull(),
    );
    expect(
      screen.getByTestId("impact-affected-T-V3-AUTH-08"),
    ).not.toBeNull();
  });
});
