// @ts-nocheck
/**
 * T-V3-C-12 / S-036 — AI 社員 組織図 screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket
 *       (T-V3-C-TEST-01). Same convention as T-V3-C-04 / C-07 / C-11.
 *
 * Covers (mapped to T-V3-C-12 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-036"
 *   structural.AC-S2  -> "h1 reads 'AI 社員 組織図'"
 *   functional.AC-F1  -> "GET /api/ai-employees/org-chart via typed client on mount"
 *   functional.AC-F2  -> "POST /api/ai-employees via typed client on create"
 *   functional.AC-F3  -> "POST /api/ai-employees/{id}/clone-from-user via typed client"
 *   functional.AC-F4  -> "4xx/5xx surfaces non-technical toast referencing endpoint"
 *   functional.AC-F5  -> "GET org-chart returns hierarchical tree → UI renders children recursively"
 *   functional.AC-F7  -> "409 from POST /api/ai-employees surfaces endpoint-referenced message"
 *   functional.AC-F8  -> "403 from clone-from-user surfaces endpoint-referenced message"
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

import AiEmployeesOrgChartPage from "@/app/(app)/ai-employees/page";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const ORG_CHART_FIXTURE = {
  tree: [
    {
      id: "emp-secretary",
      name: "Masato Secretary",
      persona: "secretary",
      hierarchy_level: 1,
      parent_id: null,
      department: "Office",
      children: [
        {
          id: "emp-mary",
          name: "Mary",
          persona: "mary",
          hierarchy_level: 2,
          parent_id: "emp-secretary",
          department: "Spec",
          children: [
            {
              id: "emp-devon",
              name: "Devon",
              persona: "devon",
              hierarchy_level: 3,
              parent_id: "emp-mary",
              department: "Dev",
              children: [],
            },
          ],
        },
        {
          id: "emp-clone-masato",
          name: "masato (clone)",
          persona: "clone",
          hierarchy_level: 3,
          parent_id: "emp-secretary",
          department: "clone",
          children: [],
        },
      ],
    },
  ],
  total: 4,
};

function defaultFetchImpl(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const method = init?.method ?? "GET";
  if (
    typeof url === "string" &&
    method === "GET" &&
    url.endsWith("/api/ai-employees/org-chart")
  ) {
    return Promise.resolve(jsonResponse(200, ORG_CHART_FIXTURE));
  }
  return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockImplementation(defaultFetchImpl);
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-036 AI 社員 組織図 page (T-V3-C-12)", () => {
  it("AC-S1: renders root with data-screen-id='S-036'", async () => {
    const { container } = render(<AiEmployeesOrgChartPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-036"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-003");
    expect(root?.getAttribute("data-task-ids")).toContain("T-V3-C-12");
    expect(root?.getAttribute("data-entities")).toBe("E-034");
  });

  it("AC-S2: h1 reads 'AI 社員 組織図'", async () => {
    render(<AiEmployeesOrgChartPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("AI 社員 組織図");
  });

  it("AC-F1: GET /api/ai-employees/org-chart on mount via typed client", async () => {
    render(<AiEmployeesOrgChartPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toContain("/api/ai-employees/org-chart");
    expect((init ?? {}).method ?? "GET").toBe("GET");
  });

  it("AC-F2: POST /api/ai-employees when the create form is submitted", async () => {
    render(<AiEmployeesOrgChartPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("create-employee-open"));

    fireEvent.change(screen.getByLabelText(/名前/), {
      target: { value: "Quinn" },
    });
    fireEvent.change(screen.getByLabelText(/ペルソナ/), {
      target: { value: "quinn" },
    });

    fetchMock.mockImplementationOnce((url: string, init?: RequestInit) => {
      if (
        typeof url === "string" &&
        url.endsWith("/api/ai-employees") &&
        init?.method === "POST"
      ) {
        return Promise.resolve(
          jsonResponse(201, { id: "emp-quinn", name: "Quinn" }),
        );
      }
      return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
    });
    // Subsequent GET refresh after success.
    fetchMock.mockImplementationOnce(defaultFetchImpl);

    fireEvent.submit(screen.getByTestId("create-employee-form"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const postCall = fetchMock.mock.calls[1];
    expect(String(postCall[0])).toContain("/api/ai-employees");
    expect(postCall[1].method).toBe("POST");
    const payload = JSON.parse(String(postCall[1].body));
    expect(payload.name).toBe("Quinn");
    expect(payload.persona).toBe("quinn");
    expect(payload.hierarchy_level).toBe(2);
    expect(payload.department).toBeTruthy();
  });

  it("AC-F3: POST /api/ai-employees/{id}/clone-from-user when the clone form is submitted", async () => {
    render(<AiEmployeesOrgChartPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("clone-from-user-open"));

    fireEvent.change(screen.getByLabelText(/クローン先 AI 社員 ID/), {
      target: { value: "emp-secretary" },
    });
    fireEvent.change(screen.getByLabelText(/ソース ユーザー ID/), {
      target: { value: "user-masato" },
    });

    fetchMock.mockImplementationOnce((url: string, init?: RequestInit) => {
      if (
        typeof url === "string" &&
        url.includes("/api/ai-employees/emp-secretary/clone-from-user") &&
        init?.method === "POST"
      ) {
        return Promise.resolve(
          jsonResponse(201, {
            id: "emp-clone-new",
            source_user_id: "user-masato",
          }),
        );
      }
      return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
    });
    fetchMock.mockImplementationOnce(defaultFetchImpl);

    fireEvent.submit(screen.getByTestId("clone-from-user-form"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const postCall = fetchMock.mock.calls[1];
    expect(String(postCall[0])).toContain(
      "/api/ai-employees/emp-secretary/clone-from-user",
    );
    expect(postCall[1].method).toBe("POST");
    const payload = JSON.parse(String(postCall[1].body));
    expect(payload.source_user_id).toBe("user-masato");
  });

  it("AC-F4: 5xx from GET org-chart surfaces a non-technical message that references the endpoint and contains no stack trace", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(500, {
          detail: {
            code: "INTERNAL",
            message:
              "Traceback (most recent call last): File '/srv/app.py' line 99",
          },
        }),
      ),
    );

    render(<AiEmployeesOrgChartPage />);

    await waitFor(() =>
      expect(screen.queryByTestId("org-chart-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("org-chart-error");
    expect(banner.textContent).toContain("/api/ai-employees/org-chart");
    expect(banner.textContent?.toLowerCase()).not.toContain("traceback");
    expect(banner.textContent?.toLowerCase()).not.toContain("/srv/app.py");
  });

  it("AC-F5: renders the hierarchical tree returned by the backend (children are recursive)", async () => {
    render(<AiEmployeesOrgChartPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    // Root + 2 children + 1 grandchild rendered by recursive OrgTreeNode.
    await waitFor(() =>
      expect(screen.queryByTestId("org-node-emp-secretary")).not.toBeNull(),
    );
    expect(screen.getByTestId("org-node-emp-mary")).not.toBeNull();
    expect(screen.getByTestId("org-node-emp-devon")).not.toBeNull();
    // Children container of the leader exposes its direct reports.
    expect(screen.getByTestId("org-children-emp-mary")).not.toBeNull();
    // Clone node is rendered in the dedicated section (not as a BMAD tree node
    // child) so the BMAD tree's secretary children only include the leader.
  });

  it("AC-F7: 409 from POST /api/ai-employees surfaces an endpoint-referenced message", async () => {
    render(<AiEmployeesOrgChartPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("create-employee-open"));
    fireEvent.change(screen.getByLabelText(/名前/), {
      target: { value: "Loop" },
    });
    fireEvent.change(screen.getByLabelText(/ペルソナ/), {
      target: { value: "loop" },
    });

    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        jsonResponse(409, {
          detail: { code: "CONFLICT", message: "circular parent reference" },
        }),
      ),
    );

    fireEvent.submit(screen.getByTestId("create-employee-form"));

    await waitFor(() =>
      expect(screen.queryByTestId("org-chart-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("org-chart-error");
    expect(banner.textContent).toContain("/api/ai-employees");
    expect(banner.textContent).toContain("循環");
  });

  it("AC-F8: 403 from clone-from-user (opt-in FALSE) surfaces an endpoint-referenced message", async () => {
    render(<AiEmployeesOrgChartPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("clone-from-user-open"));
    fireEvent.change(screen.getByLabelText(/クローン先 AI 社員 ID/), {
      target: { value: "emp-secretary" },
    });
    fireEvent.change(screen.getByLabelText(/ソース ユーザー ID/), {
      target: { value: "user-no-optin" },
    });

    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        jsonResponse(403, {
          detail: { code: "FORBIDDEN", message: "opt-in is FALSE" },
        }),
      ),
    );

    fireEvent.submit(screen.getByTestId("clone-from-user-form"));

    await waitFor(() =>
      expect(screen.queryByTestId("org-chart-error")).not.toBeNull(),
    );
    const banner = screen.getByTestId("org-chart-error");
    expect(banner.textContent).toContain("/api/ai-employees/emp-secretary/clone-from-user");
    expect(banner.textContent).toContain("権限");
  });
});
