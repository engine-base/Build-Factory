// @ts-nocheck
/**
 * T-V3-C-25 / S-064 — Personal Access Tokens screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * Covers (mapped to T-V3-C-25 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-064"
 *   structural.AC-S2  -> "h1 text equals 'Personal Access Tokens'"
 *   structural.AC-S3  -> "renders h2 'Scopes リファレンス'"
 *   functional.AC-F1  -> "5xx surfaces a non-technical toast referencing the
 *                         failing endpoint without leaking stack traces"
 *   functional.AC-F2  -> "POST /api/me/api-tokens reveals plaintext once"
 *   functional.AC-F3  -> "GET response renders only masked prefix, never plaintext"
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

import ApiTokensPage from "@/app/(app)/settings/api-tokens/page";

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

const baseTokens = {
  tokens: [
    {
      id: "tok-1",
      name: "cli-local-dev",
      prefix: "bf_pat_*****vRyM",
      scopes: ["read:tasks", "write:sessions"],
      created_at: "2026-04-22T00:00:00Z",
      expires_at: "2026-10-22T00:00:00Z",
      last_used_at: "2026-05-17T00:00:00Z",
    },
    {
      id: "tok-2",
      name: "ci-github-actions",
      prefix: "bf_pat_*****8Kpz",
      scopes: ["read:all", "write:audit"],
      created_at: "2026-04-18T00:00:00Z",
      expires_at: null,
      last_used_at: "2026-05-15T00:00:00Z",
    },
  ],
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
  fetchMock.mockResolvedValueOnce(jsonResponse(200, baseTokens));
  const utils = render(<ApiTokensPage />);
  await waitFor(() =>
    expect(
      utils.container.querySelector('[data-view-state="loaded"]'),
    ).not.toBeNull(),
  );
  return utils;
}

describe("S-064 API tokens page (T-V3-C-25)", () => {
  it("AC-S1: renders root with data-screen-id='S-064'", async () => {
    const { container } = await renderLoaded();
    const root = container.querySelector('[data-screen-id="S-064"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toContain("F-030");
  });

  it("AC-S2 + AC-S3: h1 matches mock and the section h2 'Scopes リファレンス' renders", async () => {
    await renderLoaded();
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toContain("Personal Access Tokens");
    const h2s = screen
      .getAllByRole("heading", { level: 2 })
      .map((n) => n.textContent ?? "");
    expect(h2s.some((t) => t.includes("Scopes リファレンス"))).toBe(true);
  });

  it("AC-F0: GET /api/me/api-tokens is called via typed client on mount", async () => {
    await renderLoaded();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/api/me/api-tokens");
    const init = (fetchMock.mock.calls[0][1] ?? {}) as RequestInit;
    expect(init.method).toBe("GET");
  });

  it("AC-F2: POST /api/me/api-tokens reveals plaintext token exactly once", async () => {
    const utils = await renderLoaded();
    fireEvent.click(utils.getByTestId("open-create-token"));

    const nameInput = utils.getByTestId(
      "token-name-input",
    ) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "new-cli-token" } });
    fireEvent.click(utils.getByTestId("scope-checkbox-read:tasks"));

    // Queue: 1) POST 201, 2) GET refresh 200
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, {
        token_id: "tok-new",
        plaintext_token_shown_once: "bf_pat_PLAINTEXT_VISIBLE_ONCE_xyz",
      }),
    );
    fetchMock.mockResolvedValueOnce(jsonResponse(200, baseTokens));

    fireEvent.click(utils.getByTestId("submit-create"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [postUrl, postInit] = fetchMock.mock.calls[1];
    expect(String(postUrl)).toContain("/api/me/api-tokens");
    expect((postInit as RequestInit).method).toBe("POST");
    const body = JSON.parse(String((postInit as RequestInit).body));
    expect(body.name).toBe("new-cli-token");
    expect(body.scopes).toEqual(["read:tasks"]);

    // Plaintext reveal panel surfaces the secret exactly once.
    await waitFor(() => {
      expect(utils.queryByTestId("plaintext-reveal")).not.toBeNull();
    });
    const revealed = utils.getByTestId("revealed-token-value");
    expect(revealed.textContent).toContain("bf_pat_PLAINTEXT_VISIBLE_ONCE_xyz");

    // Dismissing the panel removes the plaintext from the DOM (one-time-only).
    fireEvent.click(utils.getByTestId("dismiss-revealed"));
    await waitFor(() => {
      expect(utils.queryByTestId("plaintext-reveal")).toBeNull();
    });
  });

  it("AC-F3: GET response renders only masked prefix; never raw plaintext", async () => {
    const utils = await renderLoaded();
    const row1Prefix = utils.getByTestId("token-prefix-tok-1");
    expect(row1Prefix.textContent ?? "").toContain("*****");
    // No DOM node anywhere should contain a plaintext-looking long token from GET.
    const allText = utils.container.textContent ?? "";
    expect(allText).not.toMatch(/bf_pat_[A-Za-z0-9]{20,}/);
    // The masked prefix is present.
    expect(allText).toContain("bf_pat_*****vRyM");
  });

  it("AC-F1: 5xx GET surfaces a non-technical toast referencing /api/me/api-tokens w/o stack traces", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, {
        detail: {
          code: "INTERNAL_SERVER_ERROR",
          message:
            "Traceback (most recent call last) ... SQL FATAL psycopg2.errors.UndefinedTable",
        },
      }),
    );
    const utils = render(<ApiTokensPage />);

    await waitFor(() => {
      const toasts = utils.queryAllByTestId("toast-error");
      expect(toasts.length).toBeGreaterThan(0);
    });
    const toast = utils.getAllByTestId("toast-error")[0];
    const text = toast.textContent ?? "";
    expect(text).toContain("/api/me/api-tokens");
    expect(text).not.toMatch(/traceback/i);
    expect(text).not.toMatch(/SQL/);
    expect(text).not.toMatch(/psycopg2/i);
  });

  it("AC-revoke: DELETE /api/me/api-tokens/{id} is called on revoke button click", async () => {
    const utils = await renderLoaded();
    // confirm() is auto-accepted in beforeEach
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { revoked_at: "2026-05-17T00:00:00Z" }),
    );
    fetchMock.mockResolvedValueOnce(jsonResponse(200, baseTokens));

    fireEvent.click(utils.getByTestId("revoke-tok-1"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [delUrl, delInit] = fetchMock.mock.calls[1];
    expect(String(delUrl)).toContain("/api/me/api-tokens/tok-1");
    expect((delInit as RequestInit).method).toBe("DELETE");
  });
});
