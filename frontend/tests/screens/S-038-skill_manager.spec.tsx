// @ts-nocheck
/**
 * T-V3-C-14 / S-038 — Skill Manager screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket.
 *       Once installed, tsc strict mode picks them up automatically.
 *
 * Covers (mapped to T-V3-C-14 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-038"
 *   structural.AC-S2  -> "h1 reads 'スキルマネージャ'"
 *   functional.AC-F1  -> "GET /api/skills via typed client on mount"
 *   functional.AC-F2  -> "POST /api/skills via typed client when create-form submitted"
 *   functional.AC-F3  -> "POST /api/skills/{id}/test via typed client on テスト実行"
 *   functional.AC-F4  -> "POST /api/skills/{id}/archive via typed client on archive click"
 *   functional.AC-F5  -> "4xx/5xx surface non-technical toast w/ endpoint, no stack"
 *   functional.AC-F6  -> "GET /api/skills?category=ai → non-archived rows"
 *   functional.AC-F8  -> "POST /api/skills 403 surfaces SkillsApiError w/ '権限' message"
 *   functional.AC-F9  -> "POST /api/skills/{id}/test 429 surfaces 'リクエスト上限'"
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
  fireEvent,
  cleanup,
  act,
} from "@testing-library/react";
import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";

// next/navigation mock — page never reads router but provider safety.
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/skills",
}));

// sonner toast — assert error/success notifications.
vi.mock("sonner", () => {
  const toast = Object.assign(vi.fn(), {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  });
  return { toast };
});

// @/env stub.
vi.mock("@/env", () => ({
  env: {
    NEXT_PUBLIC_API_URL: "http://localhost:8001",
    NEXT_PUBLIC_SITE_URL: "http://localhost:3001",
  },
}));

import SkillManagerPage from "@/app/skills/page";
import { toast } from "sonner";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const SKILL_FIXTURES = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    name: "requirements-definition",
    display_name: "requirements-definition",
    description: "PM がクライアントとの要件定義セッションを進めるためのスキル",
    category: "spec",
    version: "v 1.2",
    usage_count: 87,
    archived_at: null,
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    name: "design-md",
    display_name: "design-md",
    description: "Google Labs design.md 仕様準拠のデザインシステム",
    category: "ai",
    version: "v 1.0",
    usage_count: 5,
    archived_at: null,
  },
];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <SkillManagerPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  (toast.error as ReturnType<typeof vi.fn>).mockReset();
  (toast.success as ReturnType<typeof vi.fn>).mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  if (typeof window !== "undefined") window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-038 Skill Manager page (T-V3-C-14)", () => {
  it("AC-S1: renders root with data-screen-id='S-038'", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { items: SKILL_FIXTURES, total: SKILL_FIXTURES.length }),
    );
    const { container } = renderPage();
    const root = container.querySelector('[data-screen-id="S-038"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-002");
  });

  it("AC-S2: h1 reads 'スキルマネージャ'", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { items: SKILL_FIXTURES, total: SKILL_FIXTURES.length }),
    );
    renderPage();
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("スキルマネージャ");
  });

  it("AC-F1: GET /api/skills via typed client on mount", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { items: SKILL_FIXTURES, total: SKILL_FIXTURES.length }),
    );
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/skills");
    const init = (fetchMock.mock.calls[0][1] ?? {}) as RequestInit;
    expect(init.method).toBe("GET");
  });

  it("AC-F6: GET /api/skills?category=ai when the category filter switches to 'ai'", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { items: SKILL_FIXTURES, total: SKILL_FIXTURES.length }),
    );
    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const select = screen.getByLabelText("カテゴリ") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "ai" } });

    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(1));
    const lastUrl = String(fetchMock.mock.calls.at(-1)?.[0] ?? "");
    expect(lastUrl).toContain("category=ai");
    expect(lastUrl).toContain("archived=false");
  });

  it("AC-F2: POST /api/skills via typed client when create-form submits", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).endsWith("/api/skills")) {
        return Promise.resolve(
          jsonResponse(201, { id: "new-id", name: "new-skill" }),
        );
      }
      return Promise.resolve(jsonResponse(200, { items: [], total: 0 }));
    });

    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId("open-create-skill"));
    const form = screen.getByTestId("create-skill-form") as HTMLFormElement;

    const inputs = form.querySelectorAll("input, textarea, select");
    // name
    fireEvent.change(inputs[0] as HTMLInputElement, {
      target: { value: "new-skill" },
    });
    // description (3rd field)
    fireEvent.change(inputs[2] as HTMLInputElement, {
      target: { value: "desc" },
    });
    // skill_md textarea
    const textarea = form.querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "# body" } });

    fireEvent.click(screen.getByTestId("submit-create-skill"));

    await waitFor(() => {
      const postCalls = fetchMock.mock.calls.filter(
        (c) => (c[1] as RequestInit | undefined)?.method === "POST",
      );
      expect(postCalls.length).toBeGreaterThanOrEqual(1);
      const [url, init] = postCalls[0];
      expect(String(url)).toContain("/api/skills");
      const body = JSON.parse(String(init?.body));
      expect(body.name).toBe("new-skill");
      expect(body.skill_md).toBe("# body");
    });
  });

  it("AC-F3: POST /api/skills/{id}/test when the test form submits", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/test")) {
        return Promise.resolve(
          jsonResponse(201, { output: "ok", duration_ms: 42 }),
        );
      }
      return Promise.resolve(
        jsonResponse(200, { items: SKILL_FIXTURES, total: SKILL_FIXTURES.length }),
      );
    });

    renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("skill-card-requirements-definition"),
      ).toBeTruthy(),
    );

    fireEvent.click(screen.getByTestId("test-requirements-definition"));
    const form = screen.getByTestId("test-skill-form") as HTMLFormElement;
    const input = form.querySelector("input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByTestId("submit-test-skill"));

    await waitFor(() => {
      const testCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("/test"),
      );
      expect(testCall).toBeDefined();
      const [url, init] = testCall!;
      expect(String(url)).toContain(
        "/api/skills/11111111-1111-4111-8111-111111111111/test",
      );
      expect((init as RequestInit).method).toBe("POST");
      const body = JSON.parse(String((init as RequestInit).body));
      expect(body.test_input).toBe("hello");
    });
  });

  it("AC-F4: POST /api/skills/{id}/archive when archive button clicked", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/archive")) {
        return Promise.resolve(
          jsonResponse(201, { archived_at: "2026-05-16T00:00:00Z" }),
        );
      }
      return Promise.resolve(
        jsonResponse(200, { items: SKILL_FIXTURES, total: SKILL_FIXTURES.length }),
      );
    });

    renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("skill-card-requirements-definition"),
      ).toBeTruthy(),
    );

    fireEvent.click(screen.getByTestId("archive-requirements-definition"));

    await waitFor(() => {
      const archiveCall = fetchMock.mock.calls.find((c) =>
        String(c[0]).includes("/archive"),
      );
      expect(archiveCall).toBeDefined();
      expect(String(archiveCall![0])).toContain(
        "/api/skills/11111111-1111-4111-8111-111111111111/archive",
      );
      expect((archiveCall![1] as RequestInit).method).toBe("POST");
    });
  });

  it("AC-F5: 5xx surfaces a non-technical toast referencing /api/skills w/o stack traces", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message: "Traceback (most recent call last):\n  File ...",
        },
      }),
    );
    renderPage();
    await waitFor(() =>
      expect(toast.error as ReturnType<typeof vi.fn>).toHaveBeenCalled(),
    );
    const message = String(
      (toast.error as ReturnType<typeof vi.fn>).mock.calls[0][0] ?? "",
    );
    expect(message).toContain("/api/skills");
    expect(message).not.toMatch(/traceback/i);
    expect(message).not.toMatch(/Exception/);
    expect(message).not.toMatch(/File /);
  });

  it("AC-F8: 403 on POST /api/skills surfaces 'この操作を行う権限がありません' (non-owner)", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).endsWith("/api/skills")) {
        return Promise.resolve(
          jsonResponse(403, {
            detail: { code: "FORBIDDEN", message: "RLS denied insert" },
          }),
        );
      }
      return Promise.resolve(jsonResponse(200, { items: [], total: 0 }));
    });

    renderPage();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId("open-create-skill"));
    const form = screen.getByTestId("create-skill-form") as HTMLFormElement;
    const inputs = form.querySelectorAll("input, textarea, select");
    fireEvent.change(inputs[0] as HTMLInputElement, {
      target: { value: "x" },
    });
    fireEvent.change(inputs[2] as HTMLInputElement, {
      target: { value: "d" },
    });
    const textarea = form.querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "b" } });
    fireEvent.click(screen.getByTestId("submit-create-skill"));

    await waitFor(() => {
      const calls = (toast.error as ReturnType<typeof vi.fn>).mock.calls;
      const msg = calls.map((c) => String(c[0] ?? "")).join("\n");
      expect(msg).toContain("権限");
      expect(msg).toContain("/api/skills");
      // Must NOT leak server-side details.
      expect(msg).not.toMatch(/RLS/);
    });
  });

  it("AC-F9: 429 on POST /api/skills/{id}/test surfaces 'リクエスト' / 'テスト実行' rate-limit message", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && String(url).includes("/test")) {
        return Promise.resolve(
          jsonResponse(429, {
            detail: {
              code: "RATE_LIMITED",
              message: "/test rate limit reached",
            },
          }),
        );
      }
      return Promise.resolve(
        jsonResponse(200, { items: SKILL_FIXTURES, total: SKILL_FIXTURES.length }),
      );
    });

    renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("skill-card-requirements-definition"),
      ).toBeTruthy(),
    );

    fireEvent.click(screen.getByTestId("test-requirements-definition"));
    const form = screen.getByTestId("test-skill-form") as HTMLFormElement;
    const input = form.querySelector("input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByTestId("submit-test-skill"));

    await waitFor(() => {
      const calls = (toast.error as ReturnType<typeof vi.fn>).mock.calls;
      const msg = calls.map((c) => String(c[0] ?? "")).join("\n");
      expect(msg).toContain("上限");
      expect(msg).toContain("/api/skills/{id}/test");
    });
  });
});
